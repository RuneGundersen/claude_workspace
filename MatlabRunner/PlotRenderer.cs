using System.Diagnostics;

namespace MatlabRunner;

public static class PlotRenderer
{
    private static string? _pythonExe;

    public static string? FindPython()
    {
        if (_pythonExe != null) return _pythonExe;

        // Build candidate list: PATH commands + known install locations
        var candidates = new List<string> { "python", "python3", "py" };

        // Common local install paths
        var localAppData = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var programFiles  = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        foreach (var root in new[] { localAppData, programFiles })
        {
            var pythonRoot = Path.Combine(root, "Programs", "Python");
            if (Directory.Exists(pythonRoot))
            {
                foreach (var dir in Directory.GetDirectories(pythonRoot).OrderByDescending(d => d))
                    candidates.Add(Path.Combine(dir, "python.exe"));
            }
        }

        foreach (var candidate in candidates)
        {
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = candidate,
                    Arguments = "--version",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true,
                };
                using var p = Process.Start(psi);
                p?.WaitForExit(3000);
                if (p?.ExitCode == 0) { _pythonExe = candidate; return candidate; }
            }
            catch { }
        }
        return null;
    }

    /// <summary>Returns null on success, error string on failure.</summary>
    public static async Task<string?> EnsureMatplotlibAsync(string pythonExe)
    {
        var psi = new ProcessStartInfo
        {
            FileName = pythonExe,
            Arguments = "-c \"import matplotlib\"",
            UseShellExecute = false,
            CreateNoWindow = true,
        };
        using var p = Process.Start(psi)!;
        await p.WaitForExitAsync();
        if (p.ExitCode == 0) return null;

        // Try to install
        var install = new ProcessStartInfo
        {
            FileName = pythonExe,
            Arguments = "-m pip install matplotlib --quiet",
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardError = true,
        };
        using var pip = Process.Start(install)!;
        await pip.WaitForExitAsync();
        return pip.ExitCode == 0 ? null : "Failed to install matplotlib. Run: pip install matplotlib";
    }

    public static async Task<string?> RenderAsync(string plotDataDir, CancellationToken ct)
    {
        var files = Directory.GetFiles(plotDataDir, "plot_*.json");
        if (files.Length == 0) return null;

        var python = FindPython();
        if (python == null) return "Python not found. Install Python to enable plot rendering.";

        var err = await EnsureMatplotlibAsync(python);
        if (err != null) return err;

        var scriptPath = Path.Combine(plotDataDir, "render_plots.py");
        await File.WriteAllTextAsync(scriptPath, BuildPythonScript(plotDataDir), ct);

        var psi = new ProcessStartInfo
        {
            FileName = python,
            Arguments = $"\"{scriptPath}\"",
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardError = true,
        };

        using var p = Process.Start(psi)!;
        var stderr = await p.StandardError.ReadToEndAsync(ct);
        await p.WaitForExitAsync(ct);

        return p.ExitCode == 0 ? null : $"Plot error: {stderr}";
    }

    private static string BuildPythonScript(string dataDir) => $$"""
        import json, glob, os
        import matplotlib.pyplot as plt

        data_dir = r"{{dataDir}}"
        files = sorted(glob.glob(os.path.join(data_dir, "plot_*.json")))

        if not files:
            print("No plot data.")
        else:
            fig, ax = plt.subplots(figsize=(9, 5))
            for f in files:
                with open(f) as fp:
                    d = json.load(fp)
                x = d.get("x", list(range(len(d["y"]))))
                y = d["y"]
                style = d.get("style", "-")
                label = d.get("label", None)
                ax.plot(x, y, style, label=label)
            if any(json.load(open(f)).get("label") for f in files):
                ax.legend()
            title = None
            xlabel = None
            ylabel = None
            # Check for metadata file
            meta_file = os.path.join(data_dir, "plot_meta.json")
            if os.path.exists(meta_file):
                with open(meta_file) as fp:
                    meta = json.load(fp)
                title  = meta.get("title")
                xlabel = meta.get("xlabel")
                ylabel = meta.get("ylabel")
            if title:  ax.set_title(title)
            if xlabel: ax.set_xlabel(xlabel)
            if ylabel: ax.set_ylabel(ylabel)
            ax.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.show()
        """;
}
