$ErrorActionPreference='Stop'
$private=Join-Path $env:LOCALAPPDATA 'GarinAIModelTest'
$keyFile=Join-Path $private 'typesafe-key.dpapi'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$form=New-Object Windows.Forms.Form
$form.Text='Garin - TypeSafe key (local encrypted storage)'
$form.ClientSize=New-Object Drawing.Size(550,160)
$form.StartPosition='CenterScreen'
$label=New-Object Windows.Forms.Label
$label.Text='TypeSafe API Key (hidden input). No API call. Not saved to Git.'
$label.Location=New-Object Drawing.Point(15,15)
$label.Size=New-Object Drawing.Size(520,35)
$box=New-Object Windows.Forms.TextBox
$box.Location=New-Object Drawing.Point(15,55)
$box.Size=New-Object Drawing.Size(520,28)
$box.UseSystemPasswordChar=$true
$button=New-Object Windows.Forms.Button
$button.Text='Save'
$button.Location=New-Object Drawing.Point(430,105)
$button.DialogResult=[Windows.Forms.DialogResult]::OK
$form.Controls.AddRange(@($label,$box,$button));$form.AcceptButton=$button
try {
 if($form.ShowDialog() -ne [Windows.Forms.DialogResult]::OK){exit 1}
 if([string]::IsNullOrWhiteSpace($box.Text)){throw 'Empty key'}
 $secure=New-Object Security.SecureString
 foreach($character in $box.Text.Trim().ToCharArray()){$secure.AppendChar($character)}
 $secure.MakeReadOnly()
 [IO.Directory]::CreateDirectory($private)|Out-Null
 $cipher=ConvertFrom-SecureString -SecureString $secure
 [IO.File]::WriteAllText($keyFile,$cipher,[Text.Encoding]::UTF8)
 [Windows.Forms.MessageBox]::Show('Saved locally. No API request was made.','Garin')|Out-Null
} finally {if($secure){$secure.Dispose()};$box.Clear();$form.Dispose()}
