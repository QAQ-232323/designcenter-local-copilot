@echo off
REM ============================================================
REM  Make NX and the local host share ONE review queue.
REM  NX resolves the workspace in this order:
REM      NX_SKILL_WORKSPACE -> NX2512_PROJECT_ROOT
REM      -> DC2512_PROJECT_ROOT -> ~/NXSkillWorkspace
REM  On this machine NX2512_PROJECT_ROOT points at E:\AIprojects\NXMCP,
REM  so without this variable the in-NX Review Plan dialog looks in
REM  NXMCP\review\ and reports "No plan found".
REM  The path is ASCII on purpose: a Chinese path in a .cmd file gets
REM  mangled by the console code page.
REM  Undo: review-workspace-off.cmd
REM ============================================================
setx NX_SKILL_WORKSPACE "E:\AIprojects\nx-workspace"
echo.
echo NX_SKILL_WORKSPACE = E:\AIprojects\nx-workspace
echo Restart Designcenter, then: NX Skill -^> Review Plan
echo.
pause
