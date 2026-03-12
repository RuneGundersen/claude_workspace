using System.Diagnostics;
using System.Text;

namespace MatlabRunner;

public class MatlabExecutor
{
    public string MatlabPath { get; set; } = string.Empty;

    private static readonly string TempDir = Path.Combine(Path.GetTempPath(), "MatlabRunner");
    private static readonly string OverridesDir = Path.Combine(TempDir, "overrides");
    public static readonly string PlotDataDir = Path.Combine(TempDir, "plot_data");

    public static string? AutoDetectMatlab()
    {
        var programFiles = new[]
        {
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
        };

        foreach (var root in programFiles)
        {
            var matlabRoot = Path.Combine(root, "MATLAB");
            if (!Directory.Exists(matlabRoot)) continue;

            foreach (var ver in Directory.GetDirectories(matlabRoot).OrderByDescending(d => d))
            {
                var exe = Path.Combine(ver, "bin", "matlab.exe");
                if (File.Exists(exe)) return exe;
            }
        }

        foreach (var dir in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(';'))
        {
            var exe = Path.Combine(dir.Trim(), "matlab.exe");
            if (File.Exists(exe)) return exe;
        }

        return null;
    }

    public async Task<ExecutionResult> RunAsync(string code, CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(MatlabPath) || !File.Exists(MatlabPath))
            return new ExecutionResult(false, string.Empty, "MATLAB executable not found. Set the path in Settings.");

        Directory.CreateDirectory(TempDir);
        Directory.CreateDirectory(OverridesDir);
        Directory.CreateDirectory(PlotDataDir);

        // Write plot.m override
        await WritePlotOverrideAsync(ct);

        // Clean stale plot data
        foreach (var f in Directory.GetFiles(PlotDataDir, "plot_*.json"))
            File.Delete(f);
        var metaFile = Path.Combine(PlotDataDir, "plot_meta.json");
        if (File.Exists(metaFile)) File.Delete(metaFile);

        var scriptFile = Path.Combine(TempDir, "script.m");
        var outputFile = Path.Combine(TempDir, "output.txt");

        var overridesDirM = OverridesDir.Replace("\\", "\\\\");
        var plotDataDirM  = PlotDataDir.Replace("\\", "\\\\");
        var outputFileM   = outputFile.Replace("\\", "\\\\");

        var wrappedCode = $"""
            addpath('{overridesDirM}');
            matlabrunner_plotdir__ = '{plotDataDirM}';
            diary('{outputFileM}');
            diary on;
            try
              {code}
            catch e
              fprintf(2, 'ERROR: %s\n', e.message);
            end
            diary off;
            """;

        await File.WriteAllTextAsync(scriptFile, wrappedCode, ct);

        if (File.Exists(outputFile)) File.Delete(outputFile);

        var stdout = new StringBuilder();
        var stderr = new StringBuilder();

        var psi = new ProcessStartInfo
        {
            FileName = MatlabPath,
            Arguments = $"-batch \"run('{scriptFile.Replace("\\", "\\\\")}')\"",
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };

        using var process = new Process { StartInfo = psi, EnableRaisingEvents = true };
        var tcs = new TaskCompletionSource<int>();
        process.Exited += (_, _) => tcs.TrySetResult(process.ExitCode);
        process.OutputDataReceived += (_, e) => { if (e.Data != null) stdout.AppendLine(e.Data); };
        process.ErrorDataReceived += (_, e) => { if (e.Data != null) stderr.AppendLine(e.Data); };

        ct.Register(() =>
        {
            try { if (!process.HasExited) process.Kill(entireProcessTree: true); } catch { }
            tcs.TrySetCanceled();
        });

        process.Start();
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();

        int exitCode;
        try { exitCode = await tcs.Task; }
        catch (TaskCanceledException) { return new ExecutionResult(false, string.Empty, "Execution cancelled."); }

        string output = string.Empty;
        if (File.Exists(outputFile))
            output = await File.ReadAllTextAsync(outputFile, ct);
        if (string.IsNullOrWhiteSpace(output))
            output = stdout.ToString();

        var errors = stderr.ToString();
        var success = exitCode == 0 && !errors.Contains("ERROR:");
        var hasPlots = Directory.GetFiles(PlotDataDir, "plot_*.json").Length > 0;

        return new ExecutionResult(success, output, errors, hasPlots);
    }

    private static async Task WritePlotOverrideAsync(CancellationToken ct)
    {
        var plotDataDirM = PlotDataDir.Replace("\\", "\\\\");
        var plotM = $$"""
            function varargout = plot(varargin)
                dataDir = '{{plotDataDirM}}';
                if ~exist(dataDir, 'dir'), mkdir(dataDir); end

                files = dir(fullfile(dataDir, 'plot_*.json'));
                idx = length(files) + 1;
                entry = struct();

                if nargin == 0, return; end

                if nargin >= 2 && isnumeric(varargin{2})
                    entry.x = double(varargin{1}(:)');
                    entry.y = double(varargin{2}(:)');
                    if nargin >= 3 && ischar(varargin{3})
                        entry.style = varargin{3};
                    end
                else
                    y = double(varargin{1}(:)');
                    entry.x = 1:length(y);
                    entry.y = y;
                    if nargin >= 2 && ischar(varargin{2})
                        entry.style = varargin{2};
                    end
                end

                outFile = fullfile(dataDir, sprintf('plot_%03d.json', idx));
                fid = fopen(outFile, 'w');
                fprintf(fid, '%s', jsonencode(entry));
                fclose(fid);
            end
            """;

        var titleM = $$"""
            function title(varargin)
                metaFile = fullfile('{{plotDataDirM}}', 'plot_meta.json');
                if exist(metaFile, 'file')
                    fid = fopen(metaFile, 'r'); raw = fread(fid, '*char')'; fclose(fid);
                    meta = jsondecode(raw);
                else
                    meta = struct();
                end
                meta.title = varargin{1};
                fid = fopen(metaFile, 'w'); fprintf(fid, '%s', jsonencode(meta)); fclose(fid);
            end
            """;

        var xlabelM = $$"""
            function xlabel(varargin)
                metaFile = fullfile('{{plotDataDirM}}', 'plot_meta.json');
                if exist(metaFile, 'file')
                    fid = fopen(metaFile, 'r'); raw = fread(fid, '*char')'; fclose(fid);
                    meta = jsondecode(raw);
                else
                    meta = struct();
                end
                meta.xlabel = varargin{1};
                fid = fopen(metaFile, 'w'); fprintf(fid, '%s', jsonencode(meta)); fclose(fid);
            end
            """;

        var ylabelM = $$"""
            function ylabel(varargin)
                metaFile = fullfile('{{plotDataDirM}}', 'plot_meta.json');
                if exist(metaFile, 'file')
                    fid = fopen(metaFile, 'r'); raw = fread(fid, '*char')'; fclose(fid);
                    meta = jsondecode(raw);
                else
                    meta = struct();
                end
                meta.ylabel = varargin{1};
                fid = fopen(metaFile, 'w'); fprintf(fid, '%s', jsonencode(meta)); fclose(fid);
            end
            """;

        // figure and hold are no-ops in our pipeline
        var figureM = "function varargout = figure(varargin)\nend\n";
        var holdM   = "function hold(varargin)\nend\n";

        await File.WriteAllTextAsync(Path.Combine(OverridesDir, "plot.m"),   plotM,   ct);
        await File.WriteAllTextAsync(Path.Combine(OverridesDir, "title.m"),  titleM,  ct);
        await File.WriteAllTextAsync(Path.Combine(OverridesDir, "xlabel.m"), xlabelM, ct);
        await File.WriteAllTextAsync(Path.Combine(OverridesDir, "ylabel.m"), ylabelM, ct);
        await File.WriteAllTextAsync(Path.Combine(OverridesDir, "figure.m"), figureM, ct);
        await File.WriteAllTextAsync(Path.Combine(OverridesDir, "hold.m"),   holdM,   ct);
    }
}

public record ExecutionResult(bool Success, string Output, string Errors, bool HasPlots = false);
