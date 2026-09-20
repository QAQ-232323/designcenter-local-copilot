using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Web.Script.Serialization;

using NXOpen;
using NXOpen.Features;
using NXOpen.UF;

public class NxLiveBridgeClient
{
    private static readonly int DefaultPort = ReadIntEnvOrDefault("LIVE_PORT", 25121, "NX2512_LIVE_PORT");

    // No machine paths are baked in. The NX installation root and the project
    // root are taken from the command line, then from the environment, and are
    // empty when nothing is configured: each place that genuinely needs one
    // raises an actionable error instead of using a stale default.
    private static readonly string EnvNxRoot = ReadEnv("ROOT", "NX_SKILL_NX_ROOT", "NX2512_ROOT", "DC2512_ROOT", "UGII_BASE_DIR");
    private static readonly string EnvNxBin = ReadEnv("BIN", "NX_SKILL_NX_BIN", "NX2512_BIN", "DC2512_BIN", "UGII_ROOT_DIR");
    private static readonly string DefaultNxRoot = EnvNxRoot != null ? EnvNxRoot : NxBinToRoot(EnvNxBin);
    private static readonly string ProjectRoot = ReadEnv("PROJECT_ROOT", "NX2512_PROJECT_ROOT");

    // The package root (the directory holding scripts/ and nx_runtime/) is derived
    // from where this executable lives, so the payload that ships with it is found
    // without any configuration; NX_SKILL_PLUGIN_ROOT overrides the derivation.
    private static readonly string PluginRoot = ResolvePluginRoot();
    private static readonly string GeneratedScriptRoot =
        ReadEnv("GENERATED_SCRIPT_ROOT", "NX2512_GENERATED_SCRIPT_ROOT") ?? Path.Combine(PluginRoot, @"scripts\generated");
    private static readonly bool DeleteGeneratedScripts = ReadBoolEnvOrDefault("DELETE_GENERATED_SCRIPTS", true, "NX2512_DELETE_GENERATED_SCRIPTS");

    private static string nxRoot = DefaultNxRoot;
    private static readonly JavaScriptSerializer Serializer = new JavaScriptSerializer();

    public static int Main(string[] args)
    {
        Serializer.MaxJsonLength = Int32.MaxValue;

        string command = "ping";
        string paramsJson = "{}";
        int port = DefaultPort;

        try
        {
            ParseArgs(args, ref command, ref paramsJson, ref nxRoot, ref port);
            AppDomain.CurrentDomain.AssemblyResolve += ResolveNxAssembly;
            EnsureNxRoot();

            Dictionary<string, object> parameters = ParseParams(paramsJson);
            object result = Run(command, parameters, port);
            WriteEnvelope(true, result, null, null);
            return 0;
        }
        catch (Exception ex)
        {
            WriteEnvelope(false, null, ex.Message, ex.ToString());
            return 2;
        }
    }

    private static object Run(string command, Dictionary<string, object> parameters, int port)
    {
        Session session = GetRemoteSession(port);
        string normalized = (command ?? "ping").Trim().ToLowerInvariant().Replace("_", "-");

        if (normalized == "ping")
        {
            return Ping(session, port);
        }
        if (normalized == "status")
        {
            return Status(session, port);
        }
        if (normalized == "create-modeling-part")
        {
            return CreateModelingPart(session, parameters);
        }
        if (normalized == "create-block")
        {
            return CreateBlock(session, parameters);
        }
        if (normalized == "prepare-session")
        {
            return PrepareSession(session, parameters, port);
        }
        if (normalized == "run-python")
        {
            return RunPython(session, parameters);
        }

        throw new InvalidOperationException("Unknown live command: " + command);
    }

    private static Session GetRemoteSession(int port)
    {
        string url = "http://127.0.0.1:" + port.ToString(CultureInfo.InvariantCulture) + "/NXOpenSession";
        Session session = (Session)Activator.GetObject(typeof(Session), url);
        if (session == null)
        {
            throw new InvalidOperationException("NX live bridge is not reachable at " + url + ".");
        }

        // Force a remote call so connection failures surface immediately.
        string ignored = session.GetEnvironmentVariableValue("UGII_BASE_DIR");
        return session;
    }

    private static Dictionary<string, object> Ping(Session session, int port)
    {
        Dictionary<string, object> result = new Dictionary<string, object>();
        result["message"] = "nx live bridge alive";
        result["port"] = port;
        result["ugiiBaseDir"] = SafeString(delegate { return session.GetEnvironmentVariableValue("UGII_BASE_DIR"); });
        result["applicationName"] = SafeString(delegate { return session.ApplicationName; });
        return result;
    }

    private static Dictionary<string, object> PrepareSession(Session session, Dictionary<string, object> parameters, int port)
    {
        string intent = GetString(parameters, "general", "intent");
        string targetApplication = GetString(parameters, null, "nx_application", "nxApplication", "application");
        string switchError = "";

        if (String.Equals(intent, "modeling", StringComparison.OrdinalIgnoreCase))
        {
            targetApplication = "UG_APP_MODELING";
        }
        else if (String.Equals(intent, "simulation", StringComparison.OrdinalIgnoreCase))
        {
            targetApplication = GetString(parameters, "UG_APP_SFEM", "nx_application", "nxApplication", "application");
        }

        if (!String.IsNullOrWhiteSpace(targetApplication) && targetApplication != "CAE workflow")
        {
            try
            {
                session.ApplicationSwitchImmediate(targetApplication);
            }
            catch (Exception ex)
            {
                switchError = ex.Message;
            }
        }

        Dictionary<string, object> result = Status(session, port);
        result["intent"] = intent;
        result["targetApplication"] = targetApplication;
        result["switchError"] = switchError;
        result["primaryModules"] = GetObject(parameters, new object[0], "primary_modules", "primaryModules");
        result["optionalModules"] = GetObject(parameters, new object[0], "optional_modules", "optionalModules");
        return result;
    }

    private static Dictionary<string, object> Status(Session session, int port)
    {
        Dictionary<string, object> result = new Dictionary<string, object>();
        result["port"] = port;
        result["applicationName"] = SafeString(delegate { return session.ApplicationName; });
        result["workPart"] = PartInfo(session.Parts.Work);
        result["displayPart"] = PartInfo(session.Parts.Display);
        // Keep inspection read-only and bounded. Different NX releases expose
        // different collections, so missing members are reported, not guessed.
        if (session.Parts.Work != null)
        {
            result["model"] = ModelInfo(session.Parts.Work);
        }
        return result;
    }

    private static Dictionary<string, object> ModelInfo(BasePart basePart)
    {
        Dictionary<string, object> model = new Dictionary<string, object>();
        Part part = basePart as Part;
        if (part == null)
        {
            model["available"] = false;
            model["reason"] = "Work Part is not a modeling Part";
            return model;
        }
        model["available"] = true;
        model["units"] = SafeProperty(part, "PartUnits");
        model["features"] = CollectionInfo(part, "Features", true);
        model["bodies"] = CollectionInfo(part, "Bodies", false);
        model["expressions"] = CollectionInfo(part, "Expressions", false);
        return model;
    }

    private static string SafeProperty(object target, string name)
    {
        try
        {
            PropertyInfo property = target.GetType().GetProperty(name);
            object value = property == null ? null : property.GetValue(target, null);
            return value == null ? null : Convert.ToString(value, CultureInfo.InvariantCulture);
        }
        catch (Exception) { return null; }
    }

    private static Dictionary<string, object> CollectionInfo(object part, string propertyName, bool includeNames)
    {
        Dictionary<string, object> result = new Dictionary<string, object>();
        result["available"] = false;
        try
        {
            PropertyInfo property = part.GetType().GetProperty(propertyName);
            object collection = property == null ? null : property.GetValue(part, null);
            if (collection == null) return result;
            MethodInfo toArray = collection.GetType().GetMethod("ToArray", Type.EmptyTypes);
            IEnumerable items = toArray == null ? collection as IEnumerable : toArray.Invoke(collection, null) as IEnumerable;
            if (items == null) return result;
            int count = 0;
            List<string> names = new List<string>();
            foreach (object item in items)
            {
                count++;
                if (includeNames && names.Count < 100)
                {
                    string name = SafeProperty(item, "Name");
                    if (!String.IsNullOrEmpty(name)) names.Add(name);
                }
            }
            result["available"] = true;
            result["count"] = count;
            if (includeNames)
            {
                result["names"] = names;
                result["namesTruncated"] = count > 100;
            }
        }
        catch (Exception ex) { result["reason"] = ex.Message; }
        return result;
    }

    private static Dictionary<string, object> CreateModelingPart(Session session, Dictionary<string, object> parameters)
    {
        string partPath = GetString(parameters, null, "part_path", "partPath", "path");
        if (String.IsNullOrEmpty(partPath))
        {
            partPath = Path.Combine(RequireProjectRoot("a default part path"), "nx_live_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".prt");
        }

        partPath = Path.GetFullPath(partPath);
        bool save = GetBool(parameters, true, "save");
        bool allowOverwrite = GetBool(parameters, false, "allow_overwrite", "allowOverwrite", "overwrite");

        EnsureUnderProject(partPath, "Part path");
        if (File.Exists(partPath) && !allowOverwrite)
        {
            throw new InvalidOperationException("Refusing to overwrite existing part: " + partPath);
        }

        Part part = session.Parts.NewDisplay(partPath, Part.Units.Millimeters);
        session.Parts.SetWork(part);
        PartLoadStatus loadStatus;
        session.Parts.SetDisplay(part, false, false, out loadStatus);
        if (loadStatus != null)
        {
            loadStatus.Dispose();
        }
        session.ApplicationSwitchImmediate("UG_APP_MODELING");
        part.ModelingViews.WorkView.Fit();

        if (save)
        {
            part.Save(BasePart.SaveComponents.True, BasePart.CloseAfterSave.False);
        }

        Dictionary<string, object> result = new Dictionary<string, object>();
        result["partPath"] = partPath;
        result["saved"] = save;
        result["workPart"] = PartInfo(session.Parts.Work);
        result["displayPart"] = PartInfo(session.Parts.Display);
        return result;
    }

    private static Dictionary<string, object> CreateBlock(Session session, Dictionary<string, object> parameters)
    {
        Part part = session.Parts.Work;
        if (part == null)
        {
            throw new InvalidOperationException("No work part is open in the current NX window.");
        }

        double length = GetDouble(parameters, 80.0, "length");
        double width = GetDouble(parameters, 50.0, "width");
        double height = GetDouble(parameters, 25.0, "height");
        double originX = GetDouble(parameters, 0.0, "origin_x", "originX", "x");
        double originY = GetDouble(parameters, 0.0, "origin_y", "originY", "y");
        double originZ = GetDouble(parameters, 0.0, "origin_z", "originZ", "z");
        bool save = GetBool(parameters, true, "save");

        session.ApplicationSwitchImmediate("UG_APP_MODELING");
        BlockFeatureBuilder builder = part.Features.CreateBlockFeatureBuilder(null);
        builder.SetOriginAndLengths(
            new Point3d(originX, originY, originZ),
            ToInvariant(length),
            ToInvariant(width),
            ToInvariant(height));
        Feature feature = builder.CommitFeature();
        builder.Destroy();
        part.ModelingViews.WorkView.Fit();

        if (save)
        {
            part.Save(BasePart.SaveComponents.True, BasePart.CloseAfterSave.False);
        }

        Dictionary<string, object> result = new Dictionary<string, object>();
        result["featureName"] = feature == null ? "" : feature.Name;
        result["length"] = length;
        result["width"] = width;
        result["height"] = height;
        result["origin"] = new double[] { originX, originY, originZ };
        result["saved"] = save;
        result["workPart"] = PartInfo(session.Parts.Work);
        result["displayPart"] = PartInfo(session.Parts.Display);
        return result;
    }

    private static Dictionary<string, object> RunPython(Session session, Dictionary<string, object> parameters)
    {
        string scriptPath = GetString(parameters, null, "path", "script_path", "scriptPath");
        if (String.IsNullOrEmpty(scriptPath))
        {
            throw new InvalidOperationException("Missing Python script path.");
        }

        scriptPath = Path.GetFullPath(scriptPath);
        if (!File.Exists(scriptPath))
        {
            throw new FileNotFoundException("Python script does not exist.", scriptPath);
        }

        bool allowExternal = GetBool(parameters, false, "allow_external", "allowExternal");
        bool allowDangerous = GetBool(parameters, false, "allow_dangerous", "allowDangerous");
        if (!allowExternal)
        {
            EnsureUnderProject(scriptPath, "Python script path");
        }
        if (!allowDangerous)
        {
            CheckPythonSafety(scriptPath);
        }

        string runner = Path.Combine(PluginRoot, @"nx_runtime\application\nx_run_python_payload.py");
        if (!File.Exists(runner))
        {
            throw new FileNotFoundException("Missing NX Python runner.", runner);
        }

        string payloadJson = GetString(parameters, "{}", "params_json", "paramsJson");
        string stageName = GetString(parameters, "", "stage_name", "stageName");
        bool deleteAfterRun = GetBool(parameters, DeleteGeneratedScripts, "delete_after_run", "deleteAfterRun");
        object returnValue = session.Execute(runner, null, "main", new object[] { scriptPath, payloadJson });

        bool scriptDeleted = false;
        string deleteError = "";
        if (deleteAfterRun && IsGeneratedScriptPath(scriptPath))
        {
            try
            {
                File.Delete(scriptPath);
                scriptDeleted = !File.Exists(scriptPath);
            }
            catch (Exception ex)
            {
                deleteError = ex.Message;
            }
        }

        Dictionary<string, object> result = new Dictionary<string, object>();
        result["path"] = scriptPath;
        result["stageName"] = stageName;
        result["returnValue"] = returnValue == null ? null : returnValue.ToString();
        result["applicationName"] = SafeString(delegate { return session.ApplicationName; });
        result["workPart"] = PartInfo(session.Parts.Work);
        result["displayPart"] = PartInfo(session.Parts.Display);
        result["deleteAfterRun"] = deleteAfterRun;
        result["scriptDeleted"] = scriptDeleted;
        result["deleteError"] = deleteError;
        return result;
    }

    private static bool IsGeneratedScriptPath(string scriptPath)
    {
        return IsUnderRoot(scriptPath, GeneratedScriptRoot) ||
            IsUnderRoot(scriptPath, Path.Combine(PluginRoot, @".work\generated")) ||
            IsUnderRoot(scriptPath, Path.Combine(PluginRoot, @"scripts\generated"));
    }

    private static bool IsUnderRoot(string path, string rootPath)
    {
        if (String.IsNullOrWhiteSpace(path) || String.IsNullOrWhiteSpace(rootPath))
        {
            return false;
        }
        string root = Path.GetFullPath(rootPath).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
        string fullPath = Path.GetFullPath(path);
        return fullPath.StartsWith(root, StringComparison.OrdinalIgnoreCase);
    }

    private static Dictionary<string, object> PartInfo(BasePart part)
    {
        if (part == null)
        {
            return null;
        }

        Dictionary<string, object> result = new Dictionary<string, object>();
        result["name"] = SafeString(delegate { return part.Name; });
        result["fullPath"] = SafeString(delegate { return part.FullPath; });
        return result;
    }

    private static void CheckPythonSafety(string scriptPath)
    {
        string text = File.ReadAllText(scriptPath);
        string lower = text.ToLowerInvariant();
        string[] blocked = new string[]
        {
            "os.remove",
            "os.unlink",
            "shutil.rmtree",
            "remove-item",
            ".delete(",
            "deleteobjects",
            "saveas(",
            "postprocess",
            "generate tool path",
            "generatetoolpath"
        };

        foreach (string token in blocked)
        {
            if (lower.IndexOf(token, StringComparison.Ordinal) >= 0)
            {
                throw new InvalidOperationException("Refusing to run Python script because it contains high-risk token '" + token + "'. Pass allow_dangerous=true only after reviewing it.");
            }
        }
    }

    // Paths stay inside the configured project root when one is set. With no
    // project root configured there is no boundary to enforce, so the check is
    // skipped rather than failing an explicit path the caller supplied.
    private static void EnsureUnderProject(string path, string label)
    {
        if (String.IsNullOrWhiteSpace(ProjectRoot))
        {
            return;
        }

        string root = Path.GetFullPath(ProjectRoot).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
        string fullPath = Path.GetFullPath(path);
        if (!fullPath.StartsWith(root, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(label + " must be under " + ProjectRoot + ": " + fullPath);
        }
    }

    private static string RequireProjectRoot(string purpose)
    {
        if (!String.IsNullOrWhiteSpace(ProjectRoot))
        {
            return ProjectRoot;
        }

        throw new InvalidOperationException(
            "NX skill project root is not configured, so " + purpose + " cannot be derived. " +
            "Set NX_SKILL_PROJECT_ROOT (legacy: NX2512_PROJECT_ROOT) to the directory that should hold generated parts and scripts.");
    }

    private static void EnsureNxRoot()
    {
        if (!String.IsNullOrWhiteSpace(nxRoot))
        {
            return;
        }

        throw new InvalidOperationException(
            "NX installation root is not configured. Pass -NxRoot <directory containing NXBIN>, " +
            "or set NX_SKILL_ROOT (legacy: NX2512_ROOT, DC2512_ROOT, UGII_BASE_DIR).");
    }

    private static Dictionary<string, object> ParseParams(string json)
    {
        if (String.IsNullOrWhiteSpace(json))
        {
            return new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase);
        }

        object value = Serializer.DeserializeObject(json);
        Dictionary<string, object> typed = value as Dictionary<string, object>;
        if (typed == null)
        {
            throw new InvalidOperationException("ParamsJson must be a JSON object.");
        }

        return new Dictionary<string, object>(typed, StringComparer.OrdinalIgnoreCase);
    }

    private static void ParseArgs(string[] args, ref string command, ref string paramsJson, ref string root, ref int port)
    {
        for (int i = 0; i < args.Length; i++)
        {
            string item = args[i];
            if (EqualsSwitch(item, "-Command") && i + 1 < args.Length)
            {
                command = args[++i];
            }
            else if (EqualsSwitch(item, "-ParamsJson") && i + 1 < args.Length)
            {
                paramsJson = args[++i];
            }
            else if (EqualsSwitch(item, "-ParamsJsonBase64") && i + 1 < args.Length)
            {
                byte[] bytes = Convert.FromBase64String(args[++i]);
                paramsJson = System.Text.Encoding.UTF8.GetString(bytes);
            }
            else if (EqualsSwitch(item, "-NxRoot") && i + 1 < args.Length)
            {
                root = args[++i];
            }
            else if (EqualsSwitch(item, "-Port") && i + 1 < args.Length)
            {
                port = Int32.Parse(args[++i], CultureInfo.InvariantCulture);
            }
        }

        // An explicit -NxRoot wins over every environment default.
        if (String.IsNullOrEmpty(root))
        {
            root = DefaultNxRoot;
        }
    }

    private static bool EqualsSwitch(string value, string expected)
    {
        return String.Equals(value, expected, StringComparison.OrdinalIgnoreCase);
    }

    private static string GetString(Dictionary<string, object> values, string defaultValue, params string[] names)
    {
        object value;
        foreach (string name in names)
        {
            if (values.TryGetValue(name, out value) && value != null)
            {
                return Convert.ToString(value, CultureInfo.InvariantCulture);
            }
        }
        return defaultValue;
    }

    private static object GetObject(Dictionary<string, object> values, object defaultValue, params string[] names)
    {
        object value;
        foreach (string name in names)
        {
            if (values.TryGetValue(name, out value) && value != null)
            {
                return value;
            }
        }
        return defaultValue;
    }

    private static bool GetBool(Dictionary<string, object> values, bool defaultValue, params string[] names)
    {
        object value;
        foreach (string name in names)
        {
            if (values.TryGetValue(name, out value) && value != null)
            {
                if (value is bool)
                {
                    return (bool)value;
                }
                return Boolean.Parse(Convert.ToString(value, CultureInfo.InvariantCulture));
            }
        }
        return defaultValue;
    }

    private static double GetDouble(Dictionary<string, object> values, double defaultValue, params string[] names)
    {
        object value;
        foreach (string name in names)
        {
            if (values.TryGetValue(name, out value) && value != null)
            {
                return Convert.ToDouble(value, CultureInfo.InvariantCulture);
            }
        }
        return defaultValue;
    }

    private static string ToInvariant(double value)
    {
        return value.ToString("0.################", CultureInfo.InvariantCulture);
    }

    // ---------------------------------------------------------------------
    // Settings
    //
    // Every setting is read from NX_SKILL_<NAME> first and then from the legacy
    // names used by the earlier NX2512 / DC2512 plugins, so an existing
    // installation keeps working unchanged.
    // ---------------------------------------------------------------------
    private const string EnvPrefix = "NX_SKILL_";

    private static string ReadEnv(string name, params string[] fallbackNames)
    {
        string value = Environment.GetEnvironmentVariable(EnvPrefix + name);
        if (!String.IsNullOrWhiteSpace(value))
        {
            return value.Trim();
        }

        foreach (string fallbackName in fallbackNames)
        {
            value = Environment.GetEnvironmentVariable(fallbackName);
            if (!String.IsNullOrWhiteSpace(value))
            {
                return value.Trim();
            }
        }

        return null;
    }

    private static int ReadIntEnvOrDefault(string name, int defaultValue, params string[] fallbackNames)
    {
        string value = ReadEnv(name, fallbackNames);
        int parsed;
        if (value != null && Int32.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out parsed))
        {
            return parsed;
        }

        return defaultValue;
    }

    private static bool ReadBoolEnvOrDefault(string name, bool defaultValue, params string[] fallbackNames)
    {
        string value = ReadEnv(name, fallbackNames);
        if (value == null)
        {
            return defaultValue;
        }

        string normalized = value.Trim().ToLowerInvariant();
        if (normalized == "0" || normalized == "false" || normalized == "no" || normalized == "off")
        {
            return false;
        }
        return true;
    }

    private static string NxBinToRoot(string nxBin)
    {
        if (String.IsNullOrWhiteSpace(nxBin))
        {
            return null;
        }

        string trimmed = nxBin.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        if (String.Equals(Path.GetFileName(trimmed), "NXBIN", StringComparison.OrdinalIgnoreCase))
        {
            return Path.GetDirectoryName(trimmed);
        }
        return trimmed;
    }

    private static string ResolvePluginRoot()
    {
        string configured = ReadEnv("PLUGIN_ROOT", "NX2512_PLUGIN_ROOT");
        if (!String.IsNullOrWhiteSpace(configured))
        {
            return configured;
        }

        // <package>\scripts\dotnet_bridge\bin\NxLiveBridgeClient.exe -> <package>
        try
        {
            string exeDir = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
            if (!String.IsNullOrWhiteSpace(exeDir))
            {
                DirectoryInfo bridgeDir = Directory.GetParent(exeDir);
                DirectoryInfo scriptsDir = bridgeDir == null ? null : bridgeDir.Parent;
                DirectoryInfo packageDir = scriptsDir == null ? null : scriptsDir.Parent;
                if (packageDir != null)
                {
                    return packageDir.FullName;
                }
            }
        }
        catch
        {
        }

        return "";
    }

    private delegate string StringSupplier();

    private static string SafeString(StringSupplier supplier)
    {
        try
        {
            return supplier();
        }
        catch
        {
            return "";
        }
    }

    private static Assembly ResolveNxAssembly(object sender, ResolveEventArgs args)
    {
        if (String.IsNullOrWhiteSpace(nxRoot))
        {
            return null;
        }

        string name = new AssemblyName(args.Name).Name + ".dll";
        string managedPath = Path.Combine(nxRoot, "NXBIN", "managed", name);
        if (File.Exists(managedPath))
        {
            return Assembly.LoadFrom(managedPath);
        }

        return null;
    }

    private static void WriteEnvelope(bool ok, object result, string error, string traceback)
    {
        Dictionary<string, object> envelope = new Dictionary<string, object>();
        envelope["ok"] = ok;
        if (ok)
        {
            envelope["result"] = result;
        }
        else
        {
            envelope["error"] = error;
            envelope["traceback"] = traceback;
        }

        Console.OutputEncoding = System.Text.Encoding.UTF8;
        Console.WriteLine(Serializer.Serialize(envelope));
    }
}
