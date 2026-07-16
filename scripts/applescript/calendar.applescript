property recordSeparator : ASCII character 30

on findCalendar(calendarToken)
  tell application "Calendar"
    set marker to "manage-weekly-progress:calendar:" & calendarToken
    set matches to {}
    repeat with candidate in every calendar
      try
        if (description of candidate) is marker then set end of matches to candidate
      end try
    end repeat
    if (count of matches) is 1 then return item 1 of matches
    if (count of matches) is 0 then error "MWP_NOT_OWNED:Calendar token:" & calendarToken number 1201
    error "MWP_AMBIGUOUS:Calendar token:" & calendarToken number 1202
  end tell
end findCalendar

on uniqueCalendarName(preferredName)
  tell application "Calendar"
    set existingNames to name of every calendar
    if existingNames does not contain preferredName then return preferredName
    set baseName to preferredName & " (Managed)"
    if existingNames does not contain baseName then return baseName
    set suffix to 2
    repeat
      set candidate to baseName & " " & suffix
      if existingNames does not contain candidate then return candidate
      set suffix to suffix + 1
    end repeat
  end tell
end uniqueCalendarName

on dateFromArgs(argv, firstIndex)
  set targetYear to (item firstIndex of argv) as integer
  set targetMonth to (item (firstIndex + 1) of argv) as integer
  set targetDay to (item (firstIndex + 2) of argv) as integer
  set resultDate to current date
  -- Reset the day first: keeping today's day-of-month (for example 31) while
  -- assigning a shorter target month would overflow into the next month.
  set day of resultDate to 1
  set year of resultDate to targetYear
  set month of resultDate to targetMonth
  set day of resultDate to targetDay
  set hours of resultDate to (item (firstIndex + 3) of argv) as integer
  set minutes of resultDate to (item (firstIndex + 4) of argv) as integer
  set seconds of resultDate to (item (firstIndex + 5) of argv) as integer
  -- Fail loudly instead of storing a silently shifted date.
  if (year of resultDate) is not targetYear or ((month of resultDate) as integer) is not targetMonth or (day of resultDate) is not targetDay then error "MWP_INVALID_DATE:" & targetYear & "-" & targetMonth & "-" & targetDay number 1211
  return resultDate
end dateFromArgs

on pad2(numberValue)
  set numberText to numberValue as text
  if (length of numberText) is 1 then return "0" & numberText
  return numberText
end pad2

on isoFromDate(dateValue)
  return (year of dateValue as text) & "-" & my pad2((month of dateValue) as integer) & "-" & my pad2(day of dateValue) & "T" & my pad2(hours of dateValue) & ":" & my pad2(minutes of dateValue) & ":" & my pad2(seconds of dateValue)
end isoFromDate

on matchingEventUids(targetCalendar, marker)
  tell application "Calendar"
    set matches to {}
    repeat with candidate in every event of targetCalendar
      try
        if (description of candidate) contains marker then set end of matches to uid of candidate
      end try
    end repeat
    return matches
  end tell
end matchingEventUids

on run argv
  set actionName to item 1 of argv
  do shell script "/usr/bin/open -gj -a Calendar"
  delay 1
  tell application "Calendar"
    if actionName is "doctor" then
      set writableCalendars to every calendar whose writable is true
      if (count of writableCalendars) is 0 then error "MWP_NOT_FOUND:No writable calendars" number 1203
      return "ok"
    end if

    if actionName is "ensure-calendar" then
      set knownId to item 2 of argv
      set preferredName to item 3 of argv
      if knownId is not "" then
        set targetCalendar to my findCalendar(knownId)
        set calendarToken to knownId
      else
        set calendarName to my uniqueCalendarName(preferredName)
        create calendar with name calendarName
        delay 1
        set targetCalendar to calendar calendarName
        set calendarToken to do shell script "/usr/bin/uuidgen"
        set description of targetCalendar to "manage-weekly-progress:calendar:" & calendarToken
        -- Do not try to confirm the marker here: re-reading the description in
        -- this same process returns a stale cached value even after it has
        -- persisted. Callers retry MWP_NOT_OWNED for a freshly minted token.
        delay 1
      end if
      return calendarToken & recordSeparator & (name of targetCalendar)
    end if

    if actionName is "verify-writable" then
      set targetCalendar to my findCalendar(item 2 of argv)
      if writable of targetCalendar is false then return "false"
      set probeMarker to "manage-weekly-progress:probe"
      set staleProbeUids to my matchingEventUids(targetCalendar, probeMarker)
      repeat with staleProbeUid in staleProbeUids
        try
          set staleProbe to first event of targetCalendar whose uid is staleProbeUid
          delete staleProbe
        end try
      end repeat
      set probeEvent to missing value
      try
        set probeStart to (current date) + 86400
        set probeEnd to probeStart + 60
        tell targetCalendar
          set probeEvent to make new event at end with properties {summary:"manage-weekly-progress write probe", description:probeMarker, start date:probeStart, end date:probeEnd}
        end tell
        delete probeEvent
        return "true"
      on error
        if probeEvent is not missing value then
          try
            delete probeEvent
          end try
        end if
        return "false"
      end try
    end if

    if actionName is "upsert" then
      set targetCalendar to my findCalendar(item 2 of argv)
      set itemKey to item 3 of argv
      set eventSummary to item 4 of argv
      set sourceText to item 5 of argv
      set marker to "manage-weekly-progress:item:" & itemKey
      set storedDescription to marker & linefeed & "source:" & sourceText
      set startAt to my dateFromArgs(argv, 6)
      set endAt to my dateFromArgs(argv, 12)
      set matches to my matchingEventUids(targetCalendar, marker)
      if (count of matches) > 1 then error "MWP_AMBIGUOUS:Calendar marker:" & itemKey number 1204
      if (count of matches) is 0 then
        tell targetCalendar
          set targetEvent to make new event at end with properties {summary:eventSummary, description:storedDescription, start date:startAt, end date:endAt}
        end tell
      else
        set eventUid to item 1 of matches
        set targetEvent to first event of targetCalendar whose uid is eventUid
        set summary of targetEvent to eventSummary
        set description of targetEvent to storedDescription
        set start date of targetEvent to startAt
        set end date of targetEvent to endAt
      end if
      delay 1
      return uid of targetEvent
    end if

    if actionName is "read-event" then
      set targetCalendar to my findCalendar(item 2 of argv)
      set itemKey to item 3 of argv
      set marker to "manage-weekly-progress:item:" & itemKey
      set matches to my matchingEventUids(targetCalendar, marker)
      if (count of matches) is 0 then return "MISSING"
      if (count of matches) > 1 then error "MWP_AMBIGUOUS:Calendar marker:" & itemKey number 1210
      set eventUid to item 1 of matches
      set targetEvent to first event of targetCalendar whose uid is eventUid
      return "FOUND" & recordSeparator & eventUid & recordSeparator & my isoFromDate(start date of targetEvent) & recordSeparator & my isoFromDate(end date of targetEvent)
    end if

    if actionName is "delete-event" then
      set targetCalendar to my findCalendar(item 2 of argv)
      set itemKey to item 3 of argv
      set marker to "manage-weekly-progress:item:" & itemKey
      delay 1
      set matches to my matchingEventUids(targetCalendar, marker)
      if (count of matches) is 0 then return "MISSING"
      if (count of matches) > 1 then error "MWP_AMBIGUOUS:Calendar marker:" & itemKey number 1205
      try
        set eventUid to item 1 of matches
        set targetEvent to first event of targetCalendar whose uid is eventUid
        delete targetEvent
      on error
        delay 2
        set targetCalendar to my findCalendar(item 2 of argv)
        set matches to my matchingEventUids(targetCalendar, marker)
        if (count of matches) is 0 then return "MISSING"
        if (count of matches) > 1 then error "MWP_AMBIGUOUS:Calendar marker:" & itemKey number 1205
        set eventUid to item 1 of matches
        set targetEvent to first event of targetCalendar whose uid is eventUid
        delete targetEvent
      end try
      return eventUid
    end if

    if actionName is "delete-calendar" then
      set calendarToken to item 2 of argv
      set retryDelays to {0, 1, 2, 4, 8}
      set lastErrorMessage to "MWP_SYNC_PENDING:Calendar deletion"
      set lastErrorNumber to 1206
      repeat with retryDelay in retryDelays
        if retryDelay is not 0 then delay retryDelay
        try
          set targetCalendar to my findCalendar(calendarToken)
          set targetName to name of targetCalendar
          set ownershipMarker to "manage-weekly-progress:calendar:" & calendarToken
          set namedMatches to every calendar whose name is targetName
          if (count of namedMatches) is not 1 then error "MWP_AMBIGUOUS:Calendar display name:" & targetName number 1207
          set namedTarget to item 1 of namedMatches
          if (description of namedTarget) is not ownershipMarker then error "MWP_NOT_OWNED:Calendar display name:" & targetName number 1208
          delete calendar targetName
          return "ok"
        on error errorMessage number errorNumber
          set lastErrorMessage to errorMessage
          set lastErrorNumber to errorNumber
        end try
      end repeat
      error lastErrorMessage number lastErrorNumber
    end if
  end tell
  error "Unknown Calendar action:" & actionName number 1299
end run
