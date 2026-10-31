// KeyVault.exe - tiny Windows launcher that starts main.py with pythonw.exe (no console window).
// Build: powershell -ExecutionPolicy Bypass -File tools\launcher\build.ps1
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyTitle("KeyVault Account Manager")]
[assembly: AssemblyProduct("KeyVault")]
[assembly: AssemblyVersion("1.2.0.0")]

class Launcher {
    // Resolution order: project .venv / venv -> pythonw.exe on PATH -> common install folders.
    static string FindPythonw(string baseDir) {
        string[] localVenvs = new string[] {
            Path.Combine(baseDir, ".venv", "Scripts", "pythonw.exe"),
            Path.Combine(baseDir, "venv", "Scripts", "pythonw.exe")
        };
        foreach (string p in localVenvs) {
            if (File.Exists(p)) return p;
        }

        string pathEnv = Environment.GetEnvironmentVariable("PATH") ?? "";
        foreach (string dir in pathEnv.Split(Path.PathSeparator)) {
            if (string.IsNullOrWhiteSpace(dir)) continue;
            try {
                string candidate = Path.Combine(dir.Trim(), "pythonw.exe");
                // Skip the Microsoft Store stub, which opens the Store instead of running Python.
                if (File.Exists(candidate) && !candidate.Contains("WindowsApps")) return candidate;
            } catch {}
        }

        string[] searchRoots = new string[] {
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Python"),
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
            @"C:\"
        };
        foreach (string root in searchRoots) {
            try {
                if (!Directory.Exists(root)) continue;
                string[] subdirs = Directory.GetDirectories(root, "Python*");
                Array.Sort(subdirs);
                Array.Reverse(subdirs);
                foreach (string sd in subdirs) {
                    string candidate = Path.Combine(sd, "pythonw.exe");
                    if (File.Exists(candidate)) return candidate;
                }
            } catch {}
        }
        return "pythonw.exe";
    }

    [STAThread]
    static void Main() {
        string baseDir = AppDomain.CurrentDomain.BaseDirectory;
        string mainPy = Path.Combine(baseDir, "main.py");
        if (!File.Exists(mainPy)) {
            MessageBox.Show("未找到 main.py，请确保 KeyVault.exe 位于项目根目录。", "KeyVault 启动失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }
        string pyw = FindPythonw(baseDir);
        ProcessStartInfo psi = new ProcessStartInfo();
        psi.FileName = pyw;
        psi.Arguments = "\"" + mainPy + "\"";
        psi.WorkingDirectory = baseDir;
        psi.UseShellExecute = false;
        psi.CreateNoWindow = true;
        try {
            Process.Start(psi);
        } catch (Exception ex) {
            MessageBox.Show("启动 Python 环境失败: " + ex.Message + "\n请确认已安装 Python 及 requirements.txt 依赖。", "KeyVault 启动错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
