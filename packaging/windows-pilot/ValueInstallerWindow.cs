using System;
using System.Drawing;
using System.Windows.Forms;

internal sealed class ValueInstallerWindow : Form
{
    private readonly Label status;
    private readonly Label detail;
    private readonly ProgressBar progress;
    private readonly Button close;
    private bool canClose;

    internal ValueInstallerWindow()
    {
        Text = "VALUE setup";
        Width = 560;
        Height = 245;
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = true;
        ControlBox = false;
        BackColor = Color.White;
        Font = new Font("Segoe UI", 9F, FontStyle.Regular, GraphicsUnit.Point);

        var title = new Label();
        title.AutoSize = true;
        title.Font = new Font("Segoe UI Semibold", 16F, FontStyle.Bold, GraphicsUnit.Point);
        title.Location = new Point(28, 22);
        title.Text = "Installing VALUE";

        status = new Label();
        status.Name = "installationStatus";
        status.AutoSize = false;
        status.Location = new Point(30, 70);
        status.Size = new Size(490, 24);
        status.Text = "Preparing the local installation";

        progress = new ProgressBar();
        progress.Name = "installationProgress";
        progress.Location = new Point(30, 101);
        progress.Size = new Size(490, 22);
        progress.Minimum = 0;
        progress.Maximum = 100;
        progress.Value = 0;
        progress.Style = ProgressBarStyle.Continuous;

        detail = new Label();
        detail.Name = "installationDetail";
        detail.AutoSize = false;
        detail.ForeColor = Color.FromArgb(80, 88, 100);
        detail.Location = new Point(30, 135);
        detail.Size = new Size(380, 44);
        detail.Text = "The installer is keeping the application and teaching state in an isolated local folder.";

        close = new Button();
        close.Name = "closeInstaller";
        close.Location = new Point(425, 145);
        close.Size = new Size(95, 30);
        close.Text = "Close";
        close.Enabled = false;
        close.Click += delegate { Close(); };

        Controls.Add(title);
        Controls.Add(status);
        Controls.Add(progress);
        Controls.Add(detail);
        Controls.Add(close);
        FormClosing += OnFormClosing;
    }

    internal void UpdateProgress(int value, string message)
    {
        progress.Value = Math.Max(progress.Minimum, Math.Min(progress.Maximum, value));
        status.Text = message;
        Refresh();
    }

    internal void MarkComplete(string message)
    {
        progress.Value = 100;
        status.Text = message;
        detail.Text = "The local website is opening in your browser. You can close this window.";
        canClose = true;
        ControlBox = true;
        close.Enabled = true;
        Refresh();
    }

    internal void MarkFailed(string message, string diagnosticPath)
    {
        status.Text = message;
        detail.Text = "VALUE did not finish installing. Diagnostic report: " + diagnosticPath;
        canClose = true;
        ControlBox = true;
        close.Enabled = true;
        Refresh();
    }

    private void OnFormClosing(object sender, FormClosingEventArgs args)
    {
        if (!canClose) args.Cancel = true;
    }
}
