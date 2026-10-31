; Extra steps for the installer and uninstaller (electron-builder picks this file up by itself).
;
; Uninstalling Jarvis removes everything it stored. The stock uninstaller already deletes the settings folder
; (%APPDATA%\jarvis: config.conf with the keys, the saved conversation, the Google sign-in, the speech model).
; Two things it leaves behind are removed here:
;   - %LOCALAPPDATA%\jarvis-updater, where Windows keeps a copy of the installer (about 200 MB)
;   - %LOCALAPPDATA%\jarvis, the app's cache, if one ended up there
; Installing a newer version over an old one starts the old uninstaller with --updated; then nothing is removed.
!macro customUnInstall
  ${ifNot} ${isUpdated}
    RMDir /r "$LOCALAPPDATA\${APP_PACKAGE_NAME}-updater"
    RMDir /r "$LOCALAPPDATA\${APP_FILENAME}"
  ${endIf}
!macroend
