namespace MatlabRunner;

public partial class Form1 : Form
{
    private readonly MatlabExecutor _executor = new();
    private readonly AppSettings _settings;
    private CancellationTokenSource? _cts;

    public Form1()
    {
        InitializeComponent();
        _settings = AppSettings.Load();
        ApplySettings();
        DetectOrLoadMatlab();
        CheckPython();
    }

    private void ApplySettings()
    {
        var font = new Font("Consolas", _settings.FontSize, FontStyle.Regular);
        txtCode.Font = font;
        txtOutput.Font = font;
    }

    private void DetectOrLoadMatlab()
    {
        if (!string.IsNullOrEmpty(_settings.MatlabPath) && File.Exists(_settings.MatlabPath))
        {
            _executor.MatlabPath = _settings.MatlabPath;
            UpdateStatus($"MATLAB: {_settings.MatlabPath}");
        }
        else
        {
            var detected = MatlabExecutor.AutoDetectMatlab();
            if (detected != null)
            {
                _executor.MatlabPath = detected;
                _settings.MatlabPath = detected;
                _settings.Save();
                UpdateStatus($"MATLAB auto-detected: {detected}");
            }
            else
            {
                UpdateStatus("MATLAB not found. Use Settings > Set MATLAB Path.");
            }
        }
    }

    private void CheckPython()
    {
        var python = PlotRenderer.FindPython();
        if (python == null)
            AppendOutput("[Info] Python not found — plot() calls will not render visually.\n", Color.Orange);
    }

    private async void btnRun_Click(object sender, EventArgs e)
    {
        if (string.IsNullOrWhiteSpace(txtCode.Text)) return;

        SetRunning(true);
        txtOutput.Clear();
        AppendOutput("Running...\n", Color.Gray);

        _cts = new CancellationTokenSource();

        var result = await _executor.RunAsync(txtCode.Text, _cts.Token);

        if (!string.IsNullOrWhiteSpace(result.Output))
            AppendOutput(result.Output, Color.White);

        if (!string.IsNullOrWhiteSpace(result.Errors))
            AppendOutput(result.Errors, Color.Salmon);

        if (result.Success)
            AppendOutput("\n[Done]", Color.LimeGreen);
        else if (!result.Output.Contains("ERROR") && string.IsNullOrWhiteSpace(result.Errors))
            AppendOutput("\n[Completed with warnings]", Color.Yellow);

        // Render plots with Python if any were captured
        if (result.HasPlots)
        {
            AppendOutput("\n[Rendering plot(s) with Python/matplotlib...]", Color.CornflowerBlue);
            var plotErr = await PlotRenderer.RenderAsync(MatlabExecutor.PlotDataDir, _cts.Token);
            if (plotErr != null)
                AppendOutput($"\n[Plot error] {plotErr}", Color.Salmon);
        }

        SetRunning(false);
    }

    private void btnStop_Click(object sender, EventArgs e)
    {
        _cts?.Cancel();
        AppendOutput("\n[Stopped]", Color.Orange);
        SetRunning(false);
    }

    private void btnClear_Click(object sender, EventArgs e) => txtOutput.Clear();

    private void btnClearCode_Click(object sender, EventArgs e) => txtCode.Clear();

    private void setMatlabPathToolStripMenuItem_Click(object sender, EventArgs e)
    {
        using var ofd = new OpenFileDialog
        {
            Title = "Select matlab.exe",
            Filter = "matlab.exe|matlab.exe|All executables|*.exe",
            FileName = "matlab.exe"
        };

        if (ofd.ShowDialog() == DialogResult.OK)
        {
            _executor.MatlabPath = ofd.FileName;
            _settings.MatlabPath = ofd.FileName;
            _settings.Save();
            UpdateStatus($"MATLAB: {ofd.FileName}");
        }
    }

    private void increaseFontToolStripMenuItem_Click(object sender, EventArgs e)
    {
        _settings.FontSize = Math.Min(_settings.FontSize + 1, 24);
        _settings.Save();
        ApplySettings();
    }

    private void decreaseFontToolStripMenuItem_Click(object sender, EventArgs e)
    {
        _settings.FontSize = Math.Max(_settings.FontSize - 1, 8);
        _settings.Save();
        ApplySettings();
    }

    private void SetRunning(bool running)
    {
        btnRun.Enabled = !running;
        btnStop.Enabled = running;
        progressBar.Style = running ? ProgressBarStyle.Marquee : ProgressBarStyle.Blocks;
        if (!running) progressBar.Style = ProgressBarStyle.Blocks;
    }

    private void UpdateStatus(string text) => lblStatus.Text = text;

    private void AppendOutput(string text, Color color)
    {
        txtOutput.SelectionStart = txtOutput.TextLength;
        txtOutput.SelectionLength = 0;
        txtOutput.SelectionColor = color;
        txtOutput.AppendText(text);
        txtOutput.ScrollToCaret();
    }
}
