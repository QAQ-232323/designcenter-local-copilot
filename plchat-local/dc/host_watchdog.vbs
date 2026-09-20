' ============================================================
'  host_watchdog.vbs - keep the local Copilot host running while
'  Designcenter / NX is open.
'
'  Every few seconds it does exactly two things:
'    1) asks http://127.0.0.1:<port>/api/ping whether the host is up
'    2) if not, and ugraf.exe is running, starts
'       "node server.js <port>" in a hidden window
'
'  ugraf.exe is the executable every Designcenter / NX release runs,
'  whatever the release number (2606 / 2506 / 2406 / 2306 ...), so
'  this gate is release-agnostic. It never stops a host that is
'  already up, and it never touches Designcenter itself.
'
'  Started at logon by the launcher dc\autostart-on.cmd writes into
'  the Startup folder. Stopped by dc\autostart-off.cmd.
'
'  ASCII on purpose: wscript reads a script without a BOM using the
'  ANSI code page, so non-ASCII text here would be mangled at parse
'  time (same rule as dc\*.cmd). The repo path is derived at runtime
'  from WScript.ScriptFullName instead of being written here.
'
'  NOTE antivirus: a "query processes + launch a hidden program"
'  VBScript is a pattern that AV engines flag (on this machine
'  Huorong deleted an earlier copy as TrojanDownloader/VBS.Agent.dd,
'  a false positive, on 2026-09-20). If a security tool removes this
'  file, either allow it explicitly or use the no-script fallback
'  (logon autostart of server.js via the Run key).
'
'  Optional config, host_watchdog.conf next to this file
'  (written by autostart-on.cmd; ASCII values only):
'      node=<full path to node.exe>   default: "node" from PATH
'      port=8765
'      requireDc=1                    1 = only while ugraf.exe runs
'      intervalMs=3000
'      root=<folder with server.js>   default: parent of this folder
' ============================================================
Option Explicit

Dim fso, sh, wmi
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")
Set wmi = GetObject("winmgmts:\\.\root\cimv2")

Dim here, root, nodeExe, port, requireDc, intervalMs
here = fso.GetParentFolderName(WScript.ScriptFullName)
root = fso.GetParentFolderName(here)      ' dc\ -> plchat-local\
nodeExe = "node"
port = 8765
requireDc = 1
intervalMs = 3000

Dim confPath, ts, line, eq, key, val
confPath = here & "\host_watchdog.conf"
If fso.FileExists(confPath) Then
  Set ts = fso.OpenTextFile(confPath, 1)
  Do While Not ts.AtEndOfStream
    line = Trim(ts.ReadLine)
    eq = InStr(line, "=")
    If eq > 1 And Left(line, 1) <> "#" Then
      key = LCase(Trim(Left(line, eq - 1)))
      val = Trim(Mid(line, eq + 1))
      If key = "node" Then nodeExe = val
      If key = "root" Then root = val
      If key = "port" And IsNumeric(val) Then port = CLng(val)
      If key = "requiredc" And IsNumeric(val) Then requireDc = CLng(val)
      If key = "intervalms" And IsNumeric(val) Then intervalMs = CLng(val)
    End If
  Loop
  ts.Close
End If

' Timer is seconds since midnight; the 5s gap stops a launch storm while
' a just-started node takes a moment to bind the port.
Dim lastLaunch
lastLaunch = -1000

Do
  If HostRunning() Then
    ' host is up: nothing to do
  ElseIf requireDc = 0 Or DcRunning() Then
    If (Timer - lastLaunch) > 5 Or (Timer - lastLaunch) < 0 Then
      lastLaunch = Timer
      On Error Resume Next
      sh.CurrentDirectory = root
      sh.Run """" & nodeExe & """ """ & root & "\server.js"" " & port, 0, False
      On Error GoTo 0
    End If
  End If
  WScript.Sleep intervalMs
Loop

' Any Designcenter / NX release runs as ugraf.exe.
Function DcRunning()
  Dim col
  DcRunning = False
  On Error Resume Next
  Set col = wmi.ExecQuery("SELECT Name FROM Win32_Process WHERE Name='ugraf.exe'")
  If Err.Number = 0 Then
    If col.Count > 0 Then DcRunning = True
  End If
  Err.Clear
  On Error GoTo 0
End Function

' The host answers /api/ping; a refused connection means it is down.
' server.log is not a liveness signal - it is only a stale stdout
' redirect from some earlier manual run.
Function HostRunning()
  Dim http
  HostRunning = False
  On Error Resume Next
  Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
  If Err.Number <> 0 Then
    Err.Clear
    Set http = CreateObject("MSXML2.ServerXMLHTTP")
  End If
  http.setTimeouts 400, 400, 400, 400
  http.open "GET", "http://127.0.0.1:" & port & "/api/ping", False
  http.send
  If Err.Number = 0 Then
    If http.status = 200 Then HostRunning = True
  End If
  Err.Clear
  On Error GoTo 0
End Function
