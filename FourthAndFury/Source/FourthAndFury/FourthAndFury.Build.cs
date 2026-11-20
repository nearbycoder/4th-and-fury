using UnrealBuildTool;

public class FourthAndFury : ModuleRules
{
	public FourthAndFury(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
		PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "Slate", "SlateCore", "ApplicationCore", "RenderCore", "RHI", "Json", "AssetRegistry" });
		PrivateDependencyModuleNames.AddRange(new[] { "AudioMixer", "NonRealtimeAudioRenderer", "AnimationCore" });

		// Unreal's own Apple gamepad layer stops at four pads; the game talks to GameController
		// directly so eight players can share one Mac.
		if (Target.Platform == UnrealTargetPlatform.Mac)
		{
			PublicFrameworks.Add("GameController");
		}
	}
}
