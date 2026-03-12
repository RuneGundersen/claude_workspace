# Claude Workspace

## Working Directory
All projects live in `C:\claude_workspace`.

## Projects

### MatlabRunner (`./MatlabRunner`)
.NET 8.0 WinForms app that executes MATLAB code and renders plots via Python/matplotlib.

- **Run:** `dotnet run` or launch `bin\Debug\net8.0-windows\MatlabRunner.exe`
- **Build:** `dotnet build`
- **Stack:** C# / .NET 8.0 WinForms, Python 3.12, matplotlib

#### Architecture
| File | Role |
|---|---|
| `MatlabExecutor.cs` | Runs MATLAB via `-batch`, injects `plot.m` override, captures diary output |
| `PlotRenderer.cs` | Finds Python, ensures matplotlib, renders JSON plot data |
| `AppSettings.cs` | Persists MATLAB path + font size to AppData |
| `Form1.cs` | UI logic: Run/Stop/Clear, colored output panel |

#### How plot() works
1. A custom `plot.m` (and `title.m`, `xlabel.m`, `ylabel.m`) is written to a temp override dir and prepended to MATLAB's path
2. When MATLAB runs `plot(x, y)`, the override saves data as `plot_NNN.json` instead of drawing
3. After execution, Python + matplotlib reads the JSON files and opens a figure window

## Conventions
- .NET projects target `net8.0-windows`
- Use `winget` to install tools
- Python installed at `C:\Users\runeg\AppData\Local\Programs\Python\Python312\`
