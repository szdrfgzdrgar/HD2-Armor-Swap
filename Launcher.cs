using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;
using System.Reflection;
[assembly: AssemblyTitle("HD2 Armor Swap")]
[assembly: AssemblyDescription("Free armor appearance tool by Mr-Foxington/chatgpt")]
[assembly: AssemblyCompany("Mr-Foxington/chatgpt")]
[assembly: AssemblyProduct("HD2 Armor Swap")]
[assembly: AssemblyVersion("1.2.0.0")]
[assembly: AssemblyFileVersion("1.2.0.0")]
static class Launcher {
    static string Quote(string value) {
        var b = new StringBuilder("\""); int slashes = 0;
        foreach (char c in value) {
            if (c == '\\') { slashes++; continue; }
            if (c == '"') { b.Append('\\',slashes*2+1); b.Append(c); slashes=0; continue; }
            b.Append('\\',slashes); slashes=0; b.Append(c);
        }
        b.Append('\\',slashes*2); b.Append('"'); return b.ToString();
    }
    [STAThread]
    static int Main(string[] args) {
        try {
            string root = AppDomain.CurrentDomain.BaseDirectory;
            string python = Path.Combine(root,"runtime","pythonw.exe");
            string script = Path.Combine(root,"app","main.py");
            if (!File.Exists(python) || !File.Exists(script)) {
                MessageBox.Show("Extract the entire application ZIP before starting. Keep the app and runtime folders beside this EXE.","HD2 Armor Swap",MessageBoxButtons.OK,MessageBoxIcon.Information); return 2;
            }
            var arguments = new StringBuilder("-I "+Quote(script));
            foreach (string a in args) arguments.Append(" "+Quote(a));
            var start = new ProcessStartInfo(python,arguments.ToString());
            start.WorkingDirectory=root; start.UseShellExecute=false; start.CreateNoWindow=true;
            start.WindowStyle=ProcessWindowStyle.Hidden;
            using (var p = Process.Start(start)) { p.WaitForExit(); return p.ExitCode; }
        } catch (Exception e) {
            MessageBox.Show("The application could not start.\n\n"+e.Message,"HD2 Armor Swap",MessageBoxButtons.OK,MessageBoxIcon.Error); return 1;
        }
    }
}
