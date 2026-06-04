using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Augment.BindingGen;

sealed class Param
{
    [JsonPropertyName("name")]         public string Name { get; set; } = "";
    [JsonPropertyName("type")]         public string Type { get; set; } = "";
    [JsonPropertyName("is_pointer")]   public bool IsPointer { get; set; }
    [JsonPropertyName("is_ref")]       public bool IsRef { get; set; }
    [JsonPropertyName("pointee_type")] public string PointeeType { get; set; } = "";

    public bool Opaque => IsPointer || IsRef;
}

sealed class Sym
{
    [JsonPropertyName("symbol")]       public string Symbol { get; set; } = "";
    [JsonPropertyName("short_name")]   public string ShortName { get; set; } = "";
    [JsonPropertyName("class")]        public string Class { get; set; } = "";
    [JsonPropertyName("namespace")]    public string Namespace { get; set; } = "";
    [JsonPropertyName("is_member")]    public bool IsMember { get; set; }
    [JsonPropertyName("return_type")]  public string ReturnType { get; set; } = "";
    [JsonPropertyName("returns_void")] public bool ReturnsVoid { get; set; }
    [JsonPropertyName("params")]       public List<Param> Params { get; set; } = new();
}

sealed class Manifest
{
    [JsonPropertyName("symbols")] public List<Sym> Symbols { get; set; } = new();
}

interface ILangEmitter
{
    string Lang { get; }
    string FileName { get; }
    string Generate(IReadOnlyList<Sym> symbols, string ns);
}

static class Program
{
    // Add a language here: one emitter class + one entry.
    static readonly Dictionary<string, ILangEmitter> Emitters = new()
    {
        ["cs"] = new CSharpEmitter(),
    };

    static int Main(string[] args)
    {
        string? input = null, output = null, lang = "cs", ns = "Game";
        for (int i = 0; i < args.Length; i++)
        {
            switch (args[i])
            {
                case "--in":        input  = args[++i]; break;
                case "--out":       output = args[++i]; break;
                case "--lang":      lang   = args[++i]; break;
                case "--namespace": ns     = args[++i]; break;
                default:
                    Console.Error.WriteLine($"unknown arg: {args[i]}");
                    return 2;
            }
        }

        if (input is null)
        {
            Console.Error.WriteLine("usage: AugmentBindingGen --in symbols.json [--lang cs] [--out DIR]");
            Console.Error.WriteLine($"langs: {string.Join(", ", Emitters.Keys)}");
            return 2;
        }
        if (!Emitters.TryGetValue(lang, out var emitter))
        {
            Console.Error.WriteLine($"no emitter for '{lang}' (have: {string.Join(", ", Emitters.Keys)})");
            return 2;
        }

        var manifest = JsonSerializer.Deserialize<Manifest>(File.ReadAllText(input))
                       ?? new Manifest();
        var src = emitter.Generate(manifest.Symbols, ns);

        if (output is null)
        {
            Console.Write(src);
        }
        else
        {
            var path = Directory.Exists(output) ? Path.Combine(output, emitter.FileName) : output;
            File.WriteAllText(path, src);
            Console.Error.WriteLine($"wrote {manifest.Symbols.Count} bindings -> {path}");
        }
        return 0;
    }
}
