; Per-user NSIS. Uninstall keeps userData unless the user chooses to delete it.
!macro customUnInstall
  MessageBox MB_YESNO|MB_ICONQUESTION "要从这台电脑删除 Zintriq Studio 的本地数据吗？$\n选择「否」以保留作品和数据库。" IDYES delete_user_data IDNO keep_user_data
  delete_user_data:
    RMDir /r "$APPDATA\Zintriq Studio"
    RMDir /r "$LOCALAPPDATA\Zintriq Studio"
    Goto done_user_data
  keep_user_data:
  done_user_data:
!macroend
