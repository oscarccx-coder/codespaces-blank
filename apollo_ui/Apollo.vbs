Option Explicit

Dim shell, fso, baseDir, pythonw, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = "pythonw.exe"

command = Chr(34) & pythonw & Chr(34) & " " & _
          Chr(34) & baseDir & "\launch_apollo.pyw" & Chr(34)

' 0 = hidden window, False = do not wait for program exit.
shell.Run command, 0, False
