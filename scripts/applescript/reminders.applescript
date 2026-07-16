property recordSeparator : ASCII character 30

on findList(listId)
  tell application "Reminders"
    set matches to every list whose id is listId
    if (count of matches) is 1 then return item 1 of matches
    if (count of matches) is 0 then error "MWP_NOT_OWNED:Reminders list:" & listId number 1101
    error "MWP_AMBIGUOUS:Reminders list id:" & listId number 1102
  end tell
end findList

on uniqueListName(preferredName)
  tell application "Reminders"
    set existingNames to name of every list
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
end uniqueListName

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
  if (year of resultDate) is not targetYear or ((month of resultDate) as integer) is not targetMonth or (day of resultDate) is not targetDay then error "MWP_INVALID_DATE:" & targetYear & "-" & targetMonth & "-" & targetDay number 1106
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

on matchingReminders(targetList, marker)
  tell application "Reminders"
    set matches to {}
    repeat with candidate in every reminder of targetList
      try
        if (body of candidate) contains marker then set end of matches to candidate
      end try
    end repeat
    return matches
  end tell
end matchingReminders

on run argv
  set actionName to item 1 of argv
  tell application "Reminders"
    if actionName is "doctor" then
      set listCount to count of every list
      return "ok"
    end if

    if actionName is "ensure-list" then
      set knownId to item 2 of argv
      set preferredName to item 3 of argv
      if knownId is not "" then
        set targetList to my findList(knownId)
      else
        set listName to my uniqueListName(preferredName)
        set targetList to make new list with properties {name:listName}
        delay 1
      end if
      return (id of targetList) & recordSeparator & (name of targetList)
    end if

    if actionName is "upsert" then
      set targetList to my findList(item 2 of argv)
      set itemKey to item 3 of argv
      set itemName to item 4 of argv
      set sourceText to item 5 of argv
      set marker to "manage-weekly-progress:item:" & itemKey
      set storedBody to marker & linefeed & "source:" & sourceText
      set dueAt to my dateFromArgs(argv, 6)
      set matches to my matchingReminders(targetList, marker)
      if (count of matches) > 1 then error "MWP_AMBIGUOUS:Reminder marker:" & itemKey number 1103
      if (count of matches) is 0 then
        set targetReminder to make new reminder at targetList with properties {name:itemName, body:storedBody, due date:dueAt}
      else
        set targetReminder to item 1 of matches
        set name of targetReminder to itemName
        set body of targetReminder to storedBody
        set due date of targetReminder to dueAt
        set completed of targetReminder to false
      end if
      delay 1
      return id of targetReminder
    end if

    if actionName is "read" then
      set targetList to my findList(item 2 of argv)
      set itemKey to item 3 of argv
      set marker to "manage-weekly-progress:item:" & itemKey
      set matches to my matchingReminders(targetList, marker)
      if (count of matches) is 0 then return "MISSING"
      if (count of matches) > 1 then error "MWP_AMBIGUOUS:Reminder marker:" & itemKey number 1105
      set targetReminder to item 1 of matches
      set dueText to ""
      try
        set dueText to my isoFromDate(due date of targetReminder)
      end try
      return "FOUND" & recordSeparator & (id of targetReminder) & recordSeparator & dueText & recordSeparator & ((completed of targetReminder) as text)
    end if

    if actionName is "complete" then
      set targetList to my findList(item 2 of argv)
      set itemKey to item 3 of argv
      set marker to "manage-weekly-progress:item:" & itemKey
      set matches to my matchingReminders(targetList, marker)
      if (count of matches) is 0 then return "MISSING"
      if (count of matches) > 1 then error "MWP_AMBIGUOUS:Reminder marker:" & itemKey number 1104
      set targetReminder to item 1 of matches
      set completed of targetReminder to true
      return id of targetReminder
    end if

    if actionName is "delete-list" then
      set targetList to my findList(item 2 of argv)
      delete targetList
      return "ok"
    end if
  end tell
  error "Unknown Reminders action:" & actionName number 1199
end run
