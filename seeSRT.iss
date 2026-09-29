; seeSRT 安装程序脚本（Inno Setup 6）
; 将 dist\seeSRT 整个目录打包为单一 setup.exe，
; 安装后 exe 与 _internal 依赖目录完整落盘，避免绿色解压包漏拷依赖
; 导致的 "no module named _socket" / "seeSRT 服务启动超时"。

[Setup]
AppId={{6F4B2A8E-9C1D-4E3B-8A5F-1D7C0B2E9A4F}
AppName=seeSRT
AppVersion=1.0.0
AppPublisher=Abramfreemm
DefaultDirName={localappdata}\seeSRT
DefaultGroupName=seeSRT
; 用户级安装，无需管理员权限，且程序可在自身目录写入 data\state.json
PrivilegesRequired=lowest
OutputDir=installer
OutputBaseFilename=seeSRT_setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\seeSRT.exe
WizardStyle=modern
DisableProgramGroupPage=yes
; 本应用为自包含便携程序，安装后立即可用，不提示重启
RestartIfNeededByRun=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Files]
Source: "dist\seeSRT\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\seeSRT"; Filename: "{app}\seeSRT.exe"
Name: "{group}\卸载 seeSRT"; Filename: "{uninstallexe}"
Name: "{autodesktop}\seeSRT"; Filename: "{app}\seeSRT.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式(&D)"; GroupDescription: "附加任务："

[Run]
Filename: "{app}\seeSRT.exe"; Description: "立即运行 seeSRT(&R)"; Flags: nowait postinstall skipifsilent
