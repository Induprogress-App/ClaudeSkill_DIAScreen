# Kompilacja projektu DIAScreen bez recznego klikania.
# Uzycie: powershell -ExecutionPolicy Bypass -File kompiluj.ps1 PROJEKT.dpa [WYNIK.txt]
# Kompiluje KOPIE projektu (Compile zapisuje projekt) w osobnym oknie DIAScreen: polecenie Compile (ID 50067)
# wyslane do okna, potem odczyt panelu Output (lista ID 1208) z pamieci procesu i zamkniecie tego okna.
# Okien DIAScreen otwartych przez uzytkownika nie rusza. Wynik: plik z panelem Output + podsumowanie.
param([string]$Dpa, [string]$Out = "")
$Dpa = (Resolve-Path $Dpa).Path
if (-not $Out) { $Out = [IO.Path]::ChangeExtension($Dpa, ".kompilacja.txt") }
$tmp = Join-Path $env:TEMP ("dpa_kompilacja_" + [Guid]::NewGuid().ToString("N").Substring(0, 8) + ".dpa")
Copy-Item $Dpa $tmp
Add-Type @"
using System; using System.Text; using System.Runtime.InteropServices; using System.Collections.Generic;
public class DC {
 public delegate bool EP(IntPtr h, IntPtr l);
 [DllImport("user32.dll")] static extern bool EnumWindows(EP f, IntPtr l);
 [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr p, EP f, IntPtr l);
 [DllImport("user32.dll")] static extern int GetDlgCtrlID(IntPtr h);
 [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
 [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
 [DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr h, int m, IntPtr w, IntPtr l);
 [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, int m, IntPtr w, IntPtr l);
 [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
 [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint a, bool i, uint pid);
 [DllImport("kernel32.dll")] static extern IntPtr VirtualAllocEx(IntPtr p, IntPtr a, uint s, uint t, uint pr);
 [DllImport("kernel32.dll")] static extern bool VirtualFreeEx(IntPtr p, IntPtr a, uint s, uint t);
 [DllImport("kernel32.dll")] static extern bool WriteProcessMemory(IntPtr p, IntPtr a, byte[] b, uint s, out IntPtr w);
 [DllImport("kernel32.dll")] static extern bool ReadProcessMemory(IntPtr p, IntPtr a, byte[] b, uint s, out IntPtr r);
 [DllImport("kernel32.dll")] static extern bool IsWow64Process(IntPtr p, out bool w);
 public static List<IntPtr> Tops(uint pid, string cls){ var r=new List<IntPtr>(); EnumWindows((h,l)=>{uint q; GetWindowThreadProcessId(h,out q); var b=new StringBuilder(256); GetClassName(h,b,256); if(q==pid&&IsWindowVisible(h)&&b.ToString().StartsWith(cls)) r.Add(h); return true;},IntPtr.Zero); return r; }
 public static IntPtr Find(IntPtr top, int id){ IntPtr r=IntPtr.Zero; EnumChildWindows(top,(h,l)=>{ if(GetDlgCtrlID(h)==id){r=h;return false;} return true;},IntPtr.Zero); return r; }
 public static int Count(IntPtr lv){ return (int)SendMessage(lv,0x1004,IntPtr.Zero,IntPtr.Zero); }
 public static List<string> Read(IntPtr lv){
  uint pid; GetWindowThreadProcessId(lv,out pid); IntPtr hp=OpenProcess(0x0438,false,pid);
  bool wow; IsWow64Process(hp,out wow);
  IntPtr mem=VirtualAllocEx(hp,IntPtr.Zero,8192,0x3000,4); var res=new List<string>(); IntPtr x;
  int n=Count(lv);
  for(int i=0;i<n;i++){
    byte[] it=new byte[88]; long txt=mem.ToInt64()+512;
    BitConverter.GetBytes(1).CopyTo(it,0); BitConverter.GetBytes(i).CopyTo(it,4);
    if(wow){ BitConverter.GetBytes((int)txt).CopyTo(it,20); BitConverter.GetBytes(1000).CopyTo(it,24);} else { BitConverter.GetBytes(txt).CopyTo(it,24); BitConverter.GetBytes(1000).CopyTo(it,32);}
    WriteProcessMemory(hp,mem,it,88,out x);
    int len=(int)SendMessage(lv,0x1073,(IntPtr)i,mem);
    byte[] b=new byte[2000]; ReadProcessMemory(hp,(IntPtr)txt,b,2000,out x);
    res.Add(Encoding.Unicode.GetString(b,0,Math.Max(0,len)*2)); }
  VirtualFreeEx(hp,mem,0,0x8000); return res; }
}
"@
$dir = $env:DIASCREEN_DIR
if (-not $dir) { $dir = Get-ChildItem "${env:ProgramFiles(x86)}\Delta Industrial Automation\DIAStudio\DIAScreen*", "$env:ProgramFiles\Delta Industrial Automation\DIAStudio\DIAScreen*" -ErrorAction SilentlyContinue | Sort-Object Name | Select-Object -Last 1 -ExpandProperty FullName }
$exe = Join-Path $dir "DIAScreen.exe"
if (-not (Test-Path $exe)) { "Nie znaleziono DIAScreen.exe (ustaw zmienna DIASCREEN_DIR)"; exit 2 }
$p = Start-Process $exe -ArgumentList "`"$tmp`"" -WorkingDirectory (Split-Path $exe) -PassThru
# czekanie na okno glowne z panelem Output (ID 1208)
$main = [IntPtr]::Zero
for ($i = 0; $i -lt 120; $i++) {
  Start-Sleep 2
  foreach ($h in [DC]::Tops($p.Id, "Afx:")) { $t = New-Object Text.StringBuilder 256; [void][DC]::GetWindowText($h, $t, 256); if ($t.ToString() -like "DIAScreen*" -and [DC]::Find($h, 1208) -ne [IntPtr]::Zero) { $main = $h } }
  if ($main -ne [IntPtr]::Zero) { break }
}
if ($main -eq [IntPtr]::Zero) { Stop-Process -Id $p.Id -Force; "Nie otwarto okna DIAScreen"; exit 1 }
Start-Sleep 15
$lv = [DC]::Find($main, 1208)
[void][DC]::PostMessage($main, 0x111, [IntPtr]50067, [IntPtr]::Zero)   # ID_COMPILE
$last = ""
for ($i = 0; $i -lt 180; $i++) {
  Start-Sleep 2
  $n = [DC]::Count($lv)
  if ($n -gt 3) { $r = [DC]::Read($lv); $last = $r[$r.Count - 1]; if ($last -match "Compilation (successful|failed)") { break } }
}
$r = [DC]::Read($lv)
$r | Out-File -Encoding utf8 $Out
Stop-Process -Id $p.Id -Force
Remove-Item $tmp -ErrorAction SilentlyContinue
# podsumowanie: komunikaty z ekranem i elementem, bez linii postepu
$scr = ""; $el = ""; $sum = @{}
foreach ($l in $r) {
  if ($l -match '^Screen : (\d+)') { $scr = $Matches[1]; continue }
  if ($l -match '\(\d+, \d+\)$') { $el = $l; continue }
  if (-not $l -or $l -match '^(Compiling|Save all|Check all|Compile \.\.\.|Application|Picture Data|Create Font)') { continue }
  if (-not $sum.ContainsKey($l)) { $sum[$l] = New-Object Collections.ArrayList }
  [void]$sum[$l].Add("ekran $scr $el")
}
foreach ($k in $sum.Keys) { "{0,5}x {1}" -f $sum[$k].Count, $k; $sum[$k] | Select-Object -First 5 | ForEach-Object { "         $_" } }
"Pelny wynik: $Out"
$last
