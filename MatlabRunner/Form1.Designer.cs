namespace MatlabRunner;

partial class Form1
{
    private System.ComponentModel.IContainer components = null;

    protected override void Dispose(bool disposing)
    {
        if (disposing && (components != null)) components.Dispose();
        base.Dispose(disposing);
    }

    private void InitializeComponent()
    {
        menuStrip1 = new MenuStrip();
        settingsToolStripMenuItem = new ToolStripMenuItem();
        setMatlabPathToolStripMenuItem = new ToolStripMenuItem();
        viewToolStripMenuItem = new ToolStripMenuItem();
        increaseFontToolStripMenuItem = new ToolStripMenuItem();
        decreaseFontToolStripMenuItem = new ToolStripMenuItem();
        splitContainer = new SplitContainer();
        txtCode = new RichTextBox();
        panelOutput = new Panel();
        txtOutput = new RichTextBox();
        panelOutputButtons = new Panel();
        btnClear = new Button();
        panelTop = new Panel();
        btnRun = new Button();
        btnStop = new Button();
        btnClearCode = new Button();
        progressBar = new ProgressBar();
        statusStrip = new StatusStrip();
        lblStatus = new ToolStripStatusLabel();

        menuStrip1.SuspendLayout();
        ((System.ComponentModel.ISupportInitialize)splitContainer).BeginInit();
        splitContainer.Panel1.SuspendLayout();
        splitContainer.Panel2.SuspendLayout();
        splitContainer.SuspendLayout();
        panelOutput.SuspendLayout();
        panelOutputButtons.SuspendLayout();
        panelTop.SuspendLayout();
        statusStrip.SuspendLayout();
        SuspendLayout();

        // menuStrip1
        menuStrip1.Items.AddRange(new ToolStripItem[] { settingsToolStripMenuItem, viewToolStripMenuItem });
        menuStrip1.Location = new Point(0, 0);
        menuStrip1.Size = new Size(900, 24);

        // settingsToolStripMenuItem
        settingsToolStripMenuItem.DropDownItems.AddRange(new ToolStripItem[] { setMatlabPathToolStripMenuItem });
        settingsToolStripMenuItem.Text = "Settings";

        // setMatlabPathToolStripMenuItem
        setMatlabPathToolStripMenuItem.Text = "Set MATLAB Path...";
        setMatlabPathToolStripMenuItem.Click += setMatlabPathToolStripMenuItem_Click;

        // viewToolStripMenuItem
        viewToolStripMenuItem.DropDownItems.AddRange(new ToolStripItem[] { increaseFontToolStripMenuItem, decreaseFontToolStripMenuItem });
        viewToolStripMenuItem.Text = "View";

        // increaseFontToolStripMenuItem
        increaseFontToolStripMenuItem.Text = "Increase Font (Ctrl++)";
        increaseFontToolStripMenuItem.ShortcutKeys = Keys.Control | Keys.Oemplus;
        increaseFontToolStripMenuItem.Click += increaseFontToolStripMenuItem_Click;

        // decreaseFontToolStripMenuItem
        decreaseFontToolStripMenuItem.Text = "Decrease Font (Ctrl+-)";
        decreaseFontToolStripMenuItem.ShortcutKeys = Keys.Control | Keys.OemMinus;
        decreaseFontToolStripMenuItem.Click += decreaseFontToolStripMenuItem_Click;

        // panelTop
        panelTop.Controls.AddRange(new Control[] { btnRun, btnStop, btnClearCode, progressBar });
        panelTop.Dock = DockStyle.Top;
        panelTop.Height = 42;
        panelTop.Padding = new Padding(4);
        panelTop.BackColor = Color.FromArgb(45, 45, 48);

        // btnRun
        btnRun.Text = "▶  Run  (F5)";
        btnRun.Location = new Point(8, 7);
        btnRun.Size = new Size(120, 28);
        btnRun.BackColor = Color.FromArgb(0, 122, 204);
        btnRun.ForeColor = Color.White;
        btnRun.FlatStyle = FlatStyle.Flat;
        btnRun.FlatAppearance.BorderSize = 0;
        btnRun.Click += btnRun_Click;

        // btnStop
        btnStop.Text = "■  Stop";
        btnStop.Location = new Point(136, 7);
        btnStop.Size = new Size(90, 28);
        btnStop.BackColor = Color.FromArgb(180, 50, 50);
        btnStop.ForeColor = Color.White;
        btnStop.FlatStyle = FlatStyle.Flat;
        btnStop.FlatAppearance.BorderSize = 0;
        btnStop.Enabled = false;
        btnStop.Click += btnStop_Click;

        // btnClearCode
        btnClearCode.Text = "Clear Code";
        btnClearCode.Location = new Point(234, 7);
        btnClearCode.Size = new Size(90, 28);
        btnClearCode.BackColor = Color.FromArgb(70, 70, 74);
        btnClearCode.ForeColor = Color.White;
        btnClearCode.FlatStyle = FlatStyle.Flat;
        btnClearCode.FlatAppearance.BorderSize = 0;
        btnClearCode.Click += btnClearCode_Click;

        // progressBar
        progressBar.Location = new Point(334, 12);
        progressBar.Size = new Size(200, 18);
        progressBar.Style = ProgressBarStyle.Blocks;

        // splitContainer
        splitContainer.Dock = DockStyle.Fill;
        splitContainer.Orientation = Orientation.Horizontal;
        splitContainer.SplitterDistance = 300;
        splitContainer.BackColor = Color.FromArgb(37, 37, 38);
        splitContainer.Panel1.Controls.Add(txtCode);
        splitContainer.Panel2.Controls.Add(panelOutput);

        // txtCode
        txtCode.Dock = DockStyle.Fill;
        txtCode.BackColor = Color.FromArgb(30, 30, 30);
        txtCode.ForeColor = Color.FromArgb(220, 220, 220);
        txtCode.BorderStyle = BorderStyle.None;
        txtCode.AcceptsTab = true;
        txtCode.ScrollBars = RichTextBoxScrollBars.Both;
        txtCode.WordWrap = false;
        txtCode.Text = "% Enter MATLAB code here\r\ndisp('Hello from MATLAB!');\r\nx = 1:10;\r\ndisp(x .^ 2);";
        txtCode.KeyDown += (s, e) =>
        {
            if (e.KeyCode == Keys.F5) { e.SuppressKeyPress = true; btnRun_Click(s, e); }
        };

        // panelOutput
        panelOutput.Dock = DockStyle.Fill;
        panelOutput.Controls.AddRange(new Control[] { txtOutput, panelOutputButtons });

        // panelOutputButtons
        panelOutputButtons.Dock = DockStyle.Top;
        panelOutputButtons.Height = 30;
        panelOutputButtons.BackColor = Color.FromArgb(45, 45, 48);
        panelOutputButtons.Controls.Add(btnClear);
        var lblOut = new Label
        {
            Text = "Output",
            ForeColor = Color.Gray,
            Location = new Point(6, 7),
            AutoSize = true
        };
        panelOutputButtons.Controls.Add(lblOut);

        // btnClear
        btnClear.Text = "Clear";
        btnClear.Size = new Size(60, 22);
        btnClear.Anchor = AnchorStyles.Right | AnchorStyles.Top;
        btnClear.Location = new Point(830, 4);
        btnClear.BackColor = Color.FromArgb(70, 70, 74);
        btnClear.ForeColor = Color.White;
        btnClear.FlatStyle = FlatStyle.Flat;
        btnClear.FlatAppearance.BorderSize = 0;
        btnClear.Click += btnClear_Click;

        // txtOutput
        txtOutput.Dock = DockStyle.Fill;
        txtOutput.BackColor = Color.FromArgb(20, 20, 20);
        txtOutput.ForeColor = Color.White;
        txtOutput.BorderStyle = BorderStyle.None;
        txtOutput.ReadOnly = true;
        txtOutput.ScrollBars = RichTextBoxScrollBars.Both;
        txtOutput.WordWrap = false;

        // statusStrip
        statusStrip.Items.AddRange(new ToolStripItem[] { lblStatus });
        statusStrip.BackColor = Color.FromArgb(0, 122, 204);
        lblStatus.ForeColor = Color.White;
        lblStatus.Text = "Ready";

        // Form1
        AutoScaleDimensions = new SizeF(7F, 15F);
        AutoScaleMode = AutoScaleMode.Font;
        BackColor = Color.FromArgb(37, 37, 38);
        ClientSize = new Size(900, 650);
        Controls.AddRange(new Control[] { splitContainer, panelTop, menuStrip1, statusStrip });
        MainMenuStrip = menuStrip1;
        MinimumSize = new Size(700, 500);
        Text = "MATLAB Runner";

        menuStrip1.ResumeLayout(false);
        menuStrip1.PerformLayout();
        splitContainer.Panel1.ResumeLayout(false);
        splitContainer.Panel2.ResumeLayout(false);
        splitContainer.ResumeLayout(false);
        panelOutput.ResumeLayout(false);
        panelOutputButtons.ResumeLayout(false);
        panelTop.ResumeLayout(false);
        statusStrip.ResumeLayout(false);
        statusStrip.PerformLayout();
        ResumeLayout(false);
        PerformLayout();
    }

    private MenuStrip menuStrip1;
    private ToolStripMenuItem settingsToolStripMenuItem;
    private ToolStripMenuItem setMatlabPathToolStripMenuItem;
    private ToolStripMenuItem viewToolStripMenuItem;
    private ToolStripMenuItem increaseFontToolStripMenuItem;
    private ToolStripMenuItem decreaseFontToolStripMenuItem;
    private SplitContainer splitContainer;
    private RichTextBox txtCode;
    private Panel panelOutput;
    private RichTextBox txtOutput;
    private Panel panelOutputButtons;
    private Button btnClear;
    private Panel panelTop;
    private Button btnRun;
    private Button btnStop;
    private Button btnClearCode;
    private ProgressBar progressBar;
    private StatusStrip statusStrip;
    private ToolStripStatusLabel lblStatus;
}
