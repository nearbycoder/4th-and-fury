using UnrealBuildTool;

public class FourthAndFuryTarget : TargetRules
{
	public FourthAndFuryTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.V8;
		IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_9;
		ExtraModuleNames.Add("FourthAndFury");
	}
}
