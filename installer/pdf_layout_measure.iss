; Installer di PDF Layout Measure (Inno Setup 6). Lo compila pacchetto.ps1:
;   ISCC.exe /DVersione=0.3.0 installer\pdf_layout_measure.iss
; Prende i file da dist\PDFLayoutMeasure-<versione> (preparati da pacchetto.ps1) e scrive
; dist\PDFLayoutMeasure-<versione>-setup.exe.
;
; Installa nella cartella dell'utente (%LOCALAPPDATA%\Programs\PDFLayoutMeasure): non servono
; permessi da amministratore.

#ifndef Versione
  #error Manca la versione: ISCC /DVersione=x.y.z installer\pdf_layout_measure.iss
#endif

[Setup]
AppId={{9387C797-0C3E-4CDF-9AD8-9307D8A8C228}
AppName=PDF Layout Measure
AppVersion={#Versione}
AppVerName=PDF Layout Measure {#Versione}
AppPublisher=matteo80
AppPublisherURL=https://github.com/matteo80/pdf-layout-measure
AppSupportURL=https://github.com/matteo80/pdf-layout-measure
AppUpdatesURL=https://github.com/matteo80/pdf-layout-measure/releases
AppComments=Codice scritto interamente con l'intelligenza artificiale (Claude, Anthropic)
DefaultDirName={localappdata}\Programs\PDFLayoutMeasure
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE
SetupIconFile=..\assets\icona.ico
UninstallDisplayIcon={app}\pdf_layout_measure.exe
UninstallDisplayName=PDF Layout Measure
OutputDir=..\dist
OutputBaseFilename=PDFLayoutMeasure-{#Versione}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Chiude il programma se è aperto durante l'installazione o la disinstallazione
CloseApplications=yes
ChangesAssociations=yes

[Languages]
Name: "italiano"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktop"; Description: "Crea un collegamento sul desktop"; GroupDescription: "Collegamenti:"
Name: "apricon"; Description: "Aggiungi PDF Layout Measure ad «Apri con» dei PDF (il programma predefinito non cambia)"; GroupDescription: "File:"; Flags: unchecked

[Files]
Source: "..\dist\PDFLayoutMeasure-{#Versione}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\PDF Layout Measure"; Filename: "{app}\pdf_layout_measure.exe"
Name: "{userdesktop}\PDF Layout Measure"; Filename: "{app}\pdf_layout_measure.exe"; Tasks: desktop

[Registry]
; «Apri con» per i PDF, solo per l'utente, senza toccare il programma predefinito
Root: HKCU; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "PDFLayoutMeasure.pdf"; ValueData: ""; Flags: uninsdeletevalue; Tasks: apricon
Root: HKCU; Subkey: "Software\Classes\PDFLayoutMeasure.pdf"; ValueType: string; ValueName: ""; ValueData: "Layout PDF"; Flags: uninsdeletekey; Tasks: apricon
Root: HKCU; Subkey: "Software\Classes\PDFLayoutMeasure.pdf"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "PDF Layout Measure"; Tasks: apricon
Root: HKCU; Subkey: "Software\Classes\PDFLayoutMeasure.pdf\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\pdf_layout_measure.exe,0"; Tasks: apricon
Root: HKCU; Subkey: "Software\Classes\PDFLayoutMeasure.pdf\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\pdf_layout_measure.exe"" ""%1"""; Tasks: apricon

[Run]
Filename: "{app}\pdf_layout_measure.exe"; Description: "Avvia PDF Layout Measure"; Flags: nowait postinstall skipifsilent
