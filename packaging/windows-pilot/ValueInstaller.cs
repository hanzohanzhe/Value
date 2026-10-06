using System;
using System.ComponentModel;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Windows.Forms;
using Microsoft.Win32;

internal static class ValueInstaller
{
    private const string Product = "VALUE";
    private static readonly string Root = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "VALUE");
    private static readonly string App = Path.Combine(Root, "app");
    private static readonly string State = Path.Combine(Root, "state");
    private static readonly string Uninstaller = Path.Combine(Root, "Uninstall VALUE.exe");
    private static readonly string DesktopShortcut = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "VALUE.lnk");
    private static readonly string ProgramsDirectory = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.Programs), Product);
    private const string UninstallRegistryPath =
        @"Software\Microsoft\Windows\CurrentVersion\Uninstall\VALUE";

    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length == 2 && args[0] == "--audit-payload")
        {
            try { return AuditPayload(args[1]); }
            catch { return 2; }
        }
        if (args.Length == 2 && args[0] == "--audit-payload-manifest")
        {
            try { return AuditPayloadManifest(args[1]); }
            catch { return 2; }
        }
        if (args.Length > 0 && args[0] == "--uninstall")
        {
            try { return Uninstall(); }
            catch (Exception error)
            {
                MessageBox.Show(error.Message, Product + " uninstall failed");
                return 1;
            }
        }

        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        int exitCode = 1;
        using (var window = new ValueInstallerWindow())
        {
            var worker = new BackgroundWorker();
            worker.WorkerReportsProgress = true;
            worker.DoWork += delegate(object sender, DoWorkEventArgs eventArgs)
            {
                RunInstallation((BackgroundWorker)sender);
            };
            worker.ProgressChanged += delegate(object sender, ProgressChangedEventArgs eventArgs)
            {
                window.UpdateProgress(eventArgs.ProgressPercentage, Convert.ToString(eventArgs.UserState));
            };
            worker.RunWorkerCompleted += delegate(object sender, RunWorkerCompletedEventArgs eventArgs)
            {
                if (eventArgs.Error == null)
                {
                    exitCode = 0;
                    window.MarkComplete("VALUE is ready");
                }
                else
                {
                    string diagnostic = WriteDiagnostic(eventArgs.Error);
                    window.MarkFailed(eventArgs.Error.Message, diagnostic);
                }
            };
            window.Shown += delegate { worker.RunWorkerAsync(); };
            Application.Run(window);
        }
        return exitCode;
    }

    private static int AuditPayload(string outputPath)
    {
        using (Stream resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("value-payload.zip"))
        {
            if (resource == null) throw new InvalidOperationException("The installer payload is missing.");
            using (var archive = new ZipArchive(resource, ZipArchiveMode.Read))
            using (var writer = new StreamWriter(outputPath, false, new UTF8Encoding(false)))
            using (var hasher = SHA256.Create())
            {
                foreach (ZipArchiveEntry entry in archive.Entries)
                {
                    if (String.IsNullOrEmpty(entry.Name)) continue;
                    byte[] digest;
                    using (Stream input = entry.Open()) digest = hasher.ComputeHash(input);
                    writer.Write(BitConverter.ToString(digest).Replace("-", "").ToLowerInvariant());
                    writer.Write('\t');
                    writer.Write(entry.Length);
                    writer.Write('\t');
                    writer.WriteLine(entry.FullName);
                }
            }
        }
        return 0;
    }

    private static int AuditPayloadManifest(string outputPath)
    {
        using (Stream resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("value-payload.zip"))
        {
            if (resource == null) throw new InvalidOperationException("The installer payload is missing.");
            using (var archive = new ZipArchive(resource, ZipArchiveMode.Read))
            {
                ZipArchiveEntry manifest = archive.GetEntry("VALUE-PAYLOAD-MANIFEST.json");
                if (manifest == null) throw new InvalidDataException("The payload manifest is missing.");
                using (Stream input = manifest.Open())
                using (FileStream output = new FileStream(outputPath, FileMode.Create, FileAccess.Write, FileShare.None))
                    input.CopyTo(output);
            }
        }
        return 0;
    }

    private static bool IsSafePayloadName(string name)
    {
        if (String.IsNullOrEmpty(name) || name.Contains("\\") || Path.IsPathRooted(name))
            return false;
        foreach (string part in name.Split('/'))
            if (String.IsNullOrEmpty(part) || part == "." || part == "..") return false;
        return true;
    }

    private static void RunInstallation(BackgroundWorker worker)
    {
        worker.ReportProgress(3, "Preparing the local installation");
        Directory.CreateDirectory(Root);
        bool hadPreviousApplication = Directory.Exists(App);
        string existingLauncher = Path.Combine(App, "packaging", "windows-pilot", "start-portable.ps1");
        if (File.Exists(existingLauncher))
        {
            worker.ReportProgress(7, "Stopping the previous VALUE process");
            try
            {
                int stopCode = Start(existingLauncher, "-Stop", true, 60000);
                if (stopCode != 0) throw new InvalidOperationException(
                    "The previous VALUE process did not stop cleanly.");
            }
            catch (Exception stopError)
            {
                try
                {
                    if (hadPreviousApplication) RestartPreviousApplication();
                }
                catch (Exception restartError)
                {
                    throw new AggregateException(
                        "The previous VALUE process did not stop cleanly and could not be restarted.",
                        stopError,
                        restartError
                    );
                }
                throw new InvalidOperationException(
                    "The previous VALUE process did not stop cleanly; the old application was restarted.",
                    stopError
                );
            }
        }
        InstallationMetadataSnapshot metadata = null;
        try
        {
            metadata = InstallationMetadataSnapshot.Capture(
                Uninstaller,
                DesktopShortcut,
                ProgramsDirectory,
                UninstallRegistryPath
            );
        }
        catch (Exception metadataError)
        {
            if (hadPreviousApplication) RestartPreviousApplication();
            throw new InvalidOperationException(
                "The previous VALUE metadata could not be protected; the old application was restarted.",
                metadataError
            );
        }
        using (metadata)
        {
            bool applicationPromoted = false;
            string previous = Path.Combine(Root, "app.previous");
            try
            {
                worker.ReportProgress(12, "Checking and extracting model files");
                previous = ExtractPayload(worker);
                applicationPromoted = true;
                worker.ReportProgress(82, "Starting the new VALUE service");
                int startCode = Start(
                    Path.Combine(App, "packaging", "windows-pilot", "start-portable.ps1"),
                    "-NoDialog",
                    true,
                    90000
                );
                if (startCode != 0) throw new InvalidOperationException(
                    "The VALUE service did not start. See the diagnostic path below."
                );
                worker.ReportProgress(92, "Creating shortcuts and uninstall information");
                InstallNewMetadata();
                CompleteApplicationPromotion(previous);
                metadata.Commit();
                worker.ReportProgress(100, "VALUE is ready");
            }
            catch (Exception installationError)
            {
                try
                {
                    RollbackInstallation(
                        previous,
                        applicationPromoted,
                        hadPreviousApplication,
                        metadata
                    );
                }
                catch (Exception rollbackError)
                {
                    throw new AggregateException(
                        "VALUE installation and rollback both failed.",
                        installationError,
                        rollbackError
                    );
                }
                throw;
            }
        }
    }

    private static string WriteDiagnostic(Exception error)
    {
        string diagnostics = Path.Combine(Root, "diagnostics");
        Directory.CreateDirectory(diagnostics);
        string report = Path.Combine(diagnostics, "installation-error.txt");
        File.WriteAllText(report, error.ToString());
        return report;
    }

    private static string ExtractPayload(BackgroundWorker worker)
    {
        using (Stream resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("value-payload.zip"))
        {
            if (resource == null) throw new InvalidOperationException("The installer payload is missing.");
            string staging = Path.Combine(Root, "app.new");
            string previous = Path.Combine(Root, "app.previous");
            if (Directory.Exists(staging)) Directory.Delete(staging, true);
            if (Directory.Exists(previous)) Directory.Delete(previous, true);
            Directory.CreateDirectory(staging);
            using (var archive = new ZipArchive(resource, ZipArchiveMode.Read))
            {
                string prefix = Path.GetFullPath(staging) + Path.DirectorySeparatorChar;
                long totalBytes = 0;
                foreach (ZipArchiveEntry item in archive.Entries)
                    if (!String.IsNullOrEmpty(item.Name)) totalBytes += item.Length;
                long extractedBytes = 0;
                byte[] buffer = new byte[1024 * 1024];
                foreach (ZipArchiveEntry entry in archive.Entries)
                {
                    if (!String.IsNullOrEmpty(entry.Name) && !IsSafePayloadName(entry.FullName))
                        throw new InvalidDataException("Unsafe installer member: " + entry.FullName);
                    string destination = Path.GetFullPath(Path.Combine(staging, entry.FullName));
                    if (!destination.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException("Unsafe installer member: " + entry.FullName);
                    if (String.IsNullOrEmpty(entry.Name)) { Directory.CreateDirectory(destination); continue; }
                    Directory.CreateDirectory(Path.GetDirectoryName(destination));
                    using (Stream input = entry.Open())
                    using (FileStream output = new FileStream(destination, FileMode.Create, FileAccess.Write, FileShare.None))
                    {
                        int read;
                        while ((read = input.Read(buffer, 0, buffer.Length)) > 0)
                        {
                            output.Write(buffer, 0, read);
                            extractedBytes += read;
                            int percent = totalBytes > 0
                                ? 12 + (int)Math.Min(64, (extractedBytes * 64L) / totalBytes)
                                : 76;
                            worker.ReportProgress(percent, "Extracting model files");
                        }
                    }
                }
            }
            if (Directory.Exists(App)) Directory.Move(App, previous);
            try
            {
                Directory.Move(staging, App);
            }
            catch
            {
                if (!Directory.Exists(App) && Directory.Exists(previous)) Directory.Move(previous, App);
                throw;
            }
            return previous;
        }
    }

    private static void CompleteApplicationPromotion(string previous)
    {
        try { if (Directory.Exists(previous)) Directory.Delete(previous, true); }
        catch { }
    }

    private static void InstallNewMetadata()
    {
        File.Copy(Process.GetCurrentProcess().MainModule.FileName, Uninstaller, true);
        CreateShortcuts(Uninstaller);
        RegisterUninstaller(Uninstaller);
    }

    private static void RollbackInstallation(
        string previous,
        bool applicationPromoted,
        bool hadPreviousApplication,
        InstallationMetadataSnapshot metadata)
    {
        InstallationRollbackCoordinator.Execute(
            applicationPromoted,
            hadPreviousApplication,
            delegate { RollbackApplication(previous); },
            CleanupStagingApplication,
            delegate { metadata.Restore(); },
            RestartPreviousApplication
        );
    }

    private static void CleanupStagingApplication()
    {
        string staging = Path.Combine(Root, "app.new");
        if (Directory.Exists(staging)) Directory.Delete(staging, true);
    }

    private static void RestartPreviousApplication()
    {
        string launcher = Path.Combine(
            App, "packaging", "windows-pilot", "start-portable.ps1");
        RestartApplication(launcher, App);
    }

    private static void RestartApplication(string launcher, string workingDirectory)
    {
        if (!File.Exists(launcher))
            throw new FileNotFoundException(
                "The previous VALUE launcher is missing after rollback.", launcher);
        int restartCode = Start(
            launcher, "-NoDialog", true, 90000, workingDirectory);
        if (restartCode != 0)
            throw new InvalidOperationException(
                "The previous VALUE service could not be restarted (exit code " +
                restartCode + ").");
    }

    private static void RollbackApplication(string previous)
    {
        string newLauncher = Path.Combine(App, "packaging", "windows-pilot", "start-portable.ps1");
        try
        {
            if (File.Exists(newLauncher)) Start(newLauncher, "-Stop", true);
        }
        catch { }
        if (Directory.Exists(App)) Directory.Delete(App, true);
        if (Directory.Exists(previous)) Directory.Move(previous, App);
    }

    private static void CreateShortcuts(string uninstaller)
    {
        string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        string programs = ProgramsDirectory;
        Directory.CreateDirectory(programs);
        string launcher = Path.Combine(App, "packaging", "windows-pilot", "start-portable.ps1");
        string guide = Path.Combine(App, "START-HERE-VALUE-101-Guide.pdf");
        CreateShortcut(Path.Combine(desktop, "VALUE.lnk"), "powershell.exe", "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"" + launcher + "\"");
        CreateShortcut(Path.Combine(programs, "VALUE.lnk"), "powershell.exe", "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"" + launcher + "\"");
        CreateShortcut(Path.Combine(programs, "VALUE Guide.lnk"), guide, "");
        CreateShortcut(Path.Combine(programs, "Stop VALUE.lnk"), "powershell.exe", "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"" + launcher + "\" -Stop");
        CreateShortcut(Path.Combine(programs, "Uninstall VALUE.lnk"), uninstaller, "--uninstall");
    }

    private static void CreateShortcut(string path, string target, string arguments)
    {
        Type shellType = Type.GetTypeFromProgID("WScript.Shell");
        object shell = Activator.CreateInstance(shellType);
        object shortcut = shellType.InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, shell, new object[] { path });
        Type shortcutType = shortcut.GetType();
        shortcutType.InvokeMember("TargetPath", BindingFlags.SetProperty, null, shortcut, new object[] { target });
        shortcutType.InvokeMember("Arguments", BindingFlags.SetProperty, null, shortcut, new object[] { arguments });
        shortcutType.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, shortcut, new object[] { App });
        shortcutType.InvokeMember("Save", BindingFlags.InvokeMethod, null, shortcut, null);
    }

    private static void RegisterUninstaller(string uninstaller)
    {
        using (RegistryKey key = Registry.CurrentUser.CreateSubKey(UninstallRegistryPath))
        {
            key.SetValue("DisplayName", Product);
            key.SetValue("DisplayVersion", "0.7.0-alpha.1");
            key.SetValue("Publisher", "Hanzhe Xing");
            key.SetValue("InstallLocation", Root);
            key.SetValue("UninstallString", "\"" + uninstaller + "\" --uninstall");
        }
    }

    private static int Uninstall()
    {
        try { Start(Path.Combine(App, "packaging", "windows-pilot", "start-portable.ps1"), "-Stop", true); } catch { }
        string desktop = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "VALUE.lnk");
        if (File.Exists(desktop)) File.Delete(desktop);
        string programs = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), Product);
        if (Directory.Exists(programs)) Directory.Delete(programs, true);
        Registry.CurrentUser.DeleteSubKeyTree(UninstallRegistryPath, false);
        string cleanup = CreateUninstallCleanupScript();
        Process.Start(new ProcessStartInfo("cmd.exe", "/c \"" + cleanup + "\"")
        { CreateNoWindow = true, UseShellExecute = false, WorkingDirectory = Path.GetTempPath() });
        return 0;
    }

    private static string CreateUninstallCleanupScript()
    {
        string cleanup = Path.Combine(
            Path.GetTempPath(), "value-cleanup-" + Guid.NewGuid().ToString("N") + ".cmd");
        File.WriteAllText(cleanup, "@echo off\r\ntimeout /t 2 /nobreak >nul\r\nrmdir /s /q \"" + Root + "\"\r\ndel /q \"%~f0\"\r\n");
        return cleanup;
    }

    private static int Start(string script, string arguments, bool wait = false)
    {
        return Start(script, arguments, wait, 15000);
    }

    private static int Start(string script, string arguments, bool wait, int timeoutMilliseconds)
    {
        return Start(script, arguments, wait, timeoutMilliseconds, App);
    }

    private static int Start(
        string script,
        string arguments,
        bool wait,
        int timeoutMilliseconds,
        string workingDirectory)
    {
        var info = new ProcessStartInfo("powershell.exe", "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File \"" + script + "\" " + arguments)
        { UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = workingDirectory };
        Process process = Process.Start(info);
        if (!wait) return 0;
        if (!process.WaitForExit(timeoutMilliseconds))
        {
            try { process.Kill(); } catch { }
            throw new TimeoutException("VALUE took too long to start or stop.");
        }
        return process.ExitCode;
    }
}

internal sealed class InstallationMetadataSnapshot : IDisposable
{
    private sealed class RegistryValue
    {
        internal string Name;
        internal object Value;
        internal RegistryValueKind Kind;
    }

    private readonly string backupRoot;
    private readonly string uninstaller;
    private readonly string desktopShortcut;
    private readonly string programsDirectory;
    private readonly string registryPath;
    private readonly bool hadUninstaller;
    private readonly bool hadDesktopShortcut;
    private readonly bool hadProgramsDirectory;
    private readonly bool hadRegistryKey;
    private readonly List<RegistryValue> registryValues;
    private bool committed;
    private bool restored;

    internal string BackupLocation { get { return backupRoot; } }

    private InstallationMetadataSnapshot(
        string backupRoot,
        string uninstaller,
        string desktopShortcut,
        string programsDirectory,
        string registryPath,
        bool hadUninstaller,
        bool hadDesktopShortcut,
        bool hadProgramsDirectory,
        bool hadRegistryKey,
        List<RegistryValue> registryValues)
    {
        this.backupRoot = backupRoot;
        this.uninstaller = uninstaller;
        this.desktopShortcut = desktopShortcut;
        this.programsDirectory = programsDirectory;
        this.registryPath = registryPath;
        this.hadUninstaller = hadUninstaller;
        this.hadDesktopShortcut = hadDesktopShortcut;
        this.hadProgramsDirectory = hadProgramsDirectory;
        this.hadRegistryKey = hadRegistryKey;
        this.registryValues = registryValues;
    }

    internal static InstallationMetadataSnapshot Capture(
        string uninstaller,
        string desktopShortcut,
        string programsDirectory,
        string registryPath)
    {
        string backup = Path.Combine(
            Path.GetTempPath(), "value-101-metadata-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(backup);
        bool hadUninstaller = File.Exists(uninstaller);
        bool hadDesktop = File.Exists(desktopShortcut);
        bool hadPrograms = Directory.Exists(programsDirectory);
        if (hadUninstaller) File.Copy(uninstaller, Path.Combine(backup, "uninstaller"), true);
        if (hadDesktop) File.Copy(desktopShortcut, Path.Combine(backup, "desktop.lnk"), true);
        if (hadPrograms) CopyDirectory(programsDirectory, Path.Combine(backup, "programs"));
        var values = new List<RegistryValue>();
        bool hadRegistry = false;
        using (RegistryKey key = String.IsNullOrEmpty(registryPath)
            ? null
            : Registry.CurrentUser.OpenSubKey(registryPath))
        {
            if (key != null)
            {
                hadRegistry = true;
                foreach (string name in key.GetValueNames())
                {
                    values.Add(new RegistryValue {
                        Name = name,
                        Value = key.GetValue(name, null, RegistryValueOptions.DoNotExpandEnvironmentNames),
                        Kind = key.GetValueKind(name),
                    });
                }
            }
        }
        return new InstallationMetadataSnapshot(
            backup,
            uninstaller,
            desktopShortcut,
            programsDirectory,
            registryPath,
            hadUninstaller,
            hadDesktop,
            hadPrograms,
            hadRegistry,
            values
        );
    }

    internal void Restore()
    {
        if (File.Exists(uninstaller)) File.Delete(uninstaller);
        if (File.Exists(desktopShortcut)) File.Delete(desktopShortcut);
        if (Directory.Exists(programsDirectory)) Directory.Delete(programsDirectory, true);
        if (!String.IsNullOrEmpty(registryPath))
            Registry.CurrentUser.DeleteSubKeyTree(registryPath, false);
        if (hadUninstaller)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(uninstaller));
            File.Copy(Path.Combine(backupRoot, "uninstaller"), uninstaller, true);
        }
        if (hadDesktopShortcut)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(desktopShortcut));
            File.Copy(Path.Combine(backupRoot, "desktop.lnk"), desktopShortcut, true);
        }
        if (hadProgramsDirectory)
            CopyDirectory(Path.Combine(backupRoot, "programs"), programsDirectory);
        if (hadRegistryKey && !String.IsNullOrEmpty(registryPath))
        {
            using (RegistryKey key = Registry.CurrentUser.CreateSubKey(registryPath))
            {
                foreach (RegistryValue item in registryValues)
                    key.SetValue(item.Name, item.Value, item.Kind);
            }
        }
        restored = true;
        Cleanup();
    }

    internal void Commit()
    {
        committed = true;
        Cleanup();
    }

    public void Dispose()
    {
        if (committed || restored) Cleanup();
    }

    private void Cleanup()
    {
        try { if (Directory.Exists(backupRoot)) Directory.Delete(backupRoot, true); }
        catch { if (committed) return; }
    }

    private static void CopyDirectory(string source, string destination)
    {
        Directory.CreateDirectory(destination);
        foreach (string directory in Directory.GetDirectories(source, "*", SearchOption.AllDirectories))
            Directory.CreateDirectory(directory.Replace(source, destination));
        foreach (string file in Directory.GetFiles(source, "*", SearchOption.AllDirectories))
        {
            string target = file.Replace(source, destination);
            Directory.CreateDirectory(Path.GetDirectoryName(target));
            File.Copy(file, target, true);
        }
    }
}

internal static class InstallationRollbackCoordinator
{
    internal static void Execute(
        bool applicationPromoted,
        bool hadPreviousApplication,
        Action rollbackPromotedApplication,
        Action cleanupStagingApplication,
        Action restoreMetadata,
        Action restartPreviousApplication)
    {
        var errors = new List<Exception>();
        bool applicationRestored = true;
        Action applicationAction = applicationPromoted
            ? rollbackPromotedApplication
            : cleanupStagingApplication;
        if (applicationAction != null)
        {
            try { applicationAction(); }
            catch (Exception error)
            {
                if (applicationPromoted) applicationRestored = false;
                errors.Add(error);
            }
        }
        if (restoreMetadata != null)
        {
            try { restoreMetadata(); }
            catch (Exception error) { errors.Add(error); }
        }
        if (applicationRestored && hadPreviousApplication && restartPreviousApplication != null)
        {
            try { restartPreviousApplication(); }
            catch (Exception error) { errors.Add(error); }
        }
        if (errors.Count > 0)
            throw new AggregateException("VALUE rollback was incomplete.", errors);
    }
}
