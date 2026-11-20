using UnrealBuildTool;

public class FourthAndFuryEditorTarget : TargetRules
{
	public FourthAndFuryEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.V8;
		IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_9;
		ExtraModuleNames.Add("FourthAndFury");
	}
}
