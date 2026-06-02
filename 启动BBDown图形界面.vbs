Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

baseDir = fso.GetParentFolderName(WScript.ScriptFullName)
exePath = baseDir & "\dist\BBDown\BBDown.exe"
scriptPath = baseDir & "\bbdown_launcher.pyw"
venvPythonw = baseDir & "\.venv\Scripts\pythonw.exe"

shell.CurrentDirectory = baseDir

If fso.FileExists(exePath) Then
    shell.Run """" & exePath & """", 0, False
ElseIf fso.FileExists(venvPythonw) Then
    shell.Run """" & venvPythonw & """ """ & scriptPath & """", 0, False
Else
    shell.Run "pyw -3 """ & scriptPath & """", 0, False
End If
