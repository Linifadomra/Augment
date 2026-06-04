using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace Augment;

public enum At { Head = 0, Return = 1, Overwrite = 2 }

[StructLayout(LayoutKind.Sequential)]
public unsafe struct AugmentCtx
{
    public void*  Self;
    public void** Args;
    public void*  Ret;
    public int    Cancelled;
    public void*  User;
}

[StructLayout(LayoutKind.Sequential)]
internal unsafe struct AugmentContract
{
    public byte** Affects; public int NAffects;
    public byte** Reads;   public int NReads;
    public byte** Writes;  public int NWrites;
}

[StructLayout(LayoutKind.Sequential)]
internal unsafe struct AugmentRegOpts
{
    public int   Priority;
    public byte* Tag;
    public byte* AugmentId;
    public AugmentContract Contract;
}

public static unsafe class Mixin
{
    public delegate void CtxAction(AugmentCtx* ctx);

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    delegate void NativeFn(AugmentCtx* ctx, void* userdata);

    static readonly List<NativeFn> s_alive = new();

    static Mixin()
    {
        NativeLibrary.SetDllImportResolver(typeof(Mixin).Assembly, (name, asm, search) =>
            name == "augment" ? NativeLibrary.GetMainProgramHandle() : nint.Zero);
    }

    [DllImport("augment", EntryPoint = "augment_register")]
    static extern int augment_register(
        [MarshalAs(UnmanagedType.LPUTF8Str)] string symbol,
        int phase, nint fn, nint userdata, nint opts);

    [DllImport("augment", EntryPoint = "augment_resolve")]
    static extern nint augment_resolve([MarshalAs(UnmanagedType.LPUTF8Str)] string symbol);

    public static nint Resolve(string symbol) => augment_resolve(symbol);

    public static void Register(string symbol, At at, CtxAction body,
                                int priority = 0, string? tag = null, string? id = null)
    {
        NativeFn thunk = (ctx, _) => body(ctx);
        s_alive.Add(thunk);
        nint fn = Marshal.GetFunctionPointerForDelegate(thunk);

        nint tagP = tag != null ? Marshal.StringToCoTaskMemUTF8(tag) : nint.Zero;
        nint idP  = id  != null ? Marshal.StringToCoTaskMemUTF8(id)  : nint.Zero;
        var opts = new AugmentRegOpts { Priority = priority, Tag = (byte*)tagP, AugmentId = (byte*)idP };
        augment_register(symbol, (int)at, fn, nint.Zero, (nint)(&opts));
        if (tagP != nint.Zero) Marshal.FreeCoTaskMem(tagP);
        if (idP  != nint.Zero) Marshal.FreeCoTaskMem(idP);
    }
}
