property recordSeparator : ASCII character 30

on findAccount(accountName)
  tell application "Notes"
    set matches to every account whose name is accountName
    if (count of matches) is 1 then return item 1 of matches
    if (count of matches) is 0 then error "MWP_NOT_FOUND:Notes account:" & accountName number 1001
    error "MWP_AMBIGUOUS:Notes account:" & accountName number 1002
  end tell
end findAccount

on findFolder(folderId)
  tell application "Notes"
    set foundFolders to {}
    repeat with targetAccount in every account
      set matches to every folder of targetAccount whose id is folderId
      repeat with matchFolder in matches
        set end of foundFolders to matchFolder
      end repeat
    end repeat
    if (count of foundFolders) is 1 then return item 1 of foundFolders
    if (count of foundFolders) is 0 then error "MWP_NOT_OWNED:Notes folder:" & folderId number 1003
    error "MWP_AMBIGUOUS:Notes folder id:" & folderId number 1004
  end tell
end findFolder

on uniqueFolderName(targetAccount, preferredName)
  tell application "Notes"
    set existingNames to name of every folder of targetAccount
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
end uniqueFolderName

on readUtf8File(filePath)
  return (read POSIX file filePath as «class utf8») as text
end readUtf8File

on run argv
  set actionName to item 1 of argv
  tell application "Notes"
    if actionName is "doctor" then
      set accountNames to name of every account
      if (count of accountNames) is 0 then error "MWP_NOT_FOUND:No Notes accounts" number 1005
      return "ok"
    end if

    if actionName is "ensure-folder" then
      set accountName to item 2 of argv
      set knownId to item 3 of argv
      set preferredName to item 4 of argv
      set targetAccount to my findAccount(accountName)
      if knownId is not "" then
        set targetFolder to my findFolder(knownId)
      else
        set folderName to my uniqueFolderName(targetAccount, preferredName)
        set targetFolder to make new folder at targetAccount with properties {name:folderName}
        delay 1
      end if
      return (id of targetFolder) & recordSeparator & (name of targetFolder)
    end if

    if actionName is "read-note" then
      set targetFolder to my findFolder(item 2 of argv)
      set noteTitle to item 3 of argv
      set candidates to every note of targetFolder whose name is noteTitle
      if (count of candidates) is 0 then return "MISSING"
      if (count of candidates) > 1 then error "MWP_AMBIGUOUS:Note title:" & noteTitle number 1006
      set targetNote to item 1 of candidates
      return "FOUND" & recordSeparator & (id of targetNote) & recordSeparator & (body of targetNote)
    end if

    if actionName is "read-by-id" then
      set targetFolder to my findFolder(item 2 of argv)
      set noteId to item 3 of argv
      set candidates to every note of targetFolder whose id is noteId
      if (count of candidates) is 0 then error "MWP_NOT_OWNED:Note:" & noteId number 1007
      if (count of candidates) > 1 then error "MWP_AMBIGUOUS:Note id:" & noteId number 1008
      set targetNote to item 1 of candidates
      return "FOUND" & recordSeparator & (id of targetNote) & recordSeparator & (body of targetNote)
    end if

    if actionName is "create-note" then
      set targetFolder to my findFolder(item 2 of argv)
      set noteTitle to item 3 of argv
      if (count of (every note of targetFolder whose name is noteTitle)) > 0 then error "MWP_AMBIGUOUS:Note already exists:" & noteTitle number 1009
      set bodyText to my readUtf8File(item 4 of argv)
      set targetNote to make new note at targetFolder with properties {name:noteTitle, body:bodyText}
      delay 1
      return (id of targetNote) & recordSeparator & (body of targetNote)
    end if

    if actionName is "write-note" then
      set targetFolder to my findFolder(item 2 of argv)
      set noteId to item 3 of argv
      set candidates to every note of targetFolder whose id is noteId
      if (count of candidates) is not 1 then error "MWP_NOT_OWNED:Note:" & noteId number 1010
      set targetNote to item 1 of candidates
      set expectedBody to my readUtf8File(item 4 of argv)
      set currentBody to body of targetNote
      -- AppleScript text comparison ignores case by default; a case-only
      -- manual edit must still be detected as a conflict.
      considering case
        set bodyUnchanged to (currentBody is expectedBody)
      end considering
      if not bodyUnchanged then error "MWP_CONFLICT:Note changed since read:" & noteId & ":current=" & (length of currentBody) & ":expected=" & (length of expectedBody) number 1011
      set body of targetNote to my readUtf8File(item 5 of argv)
      delay 1
      return (id of targetNote) & recordSeparator & (body of targetNote)
    end if

    if actionName is "delete-note" then
      set targetFolder to my findFolder(item 2 of argv)
      set noteId to item 3 of argv
      set candidates to every note of targetFolder whose id is noteId
      if (count of candidates) is 1 then delete item 1 of candidates
      return "ok"
    end if

    if actionName is "delete-folder" then
      set targetFolder to my findFolder(item 2 of argv)
      delete targetFolder
      return "ok"
    end if
  end tell
  error "Unknown Notes action:" & actionName number 1099
end run
