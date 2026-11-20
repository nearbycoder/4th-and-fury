#include "FuryStadium.h"

#include "Components/ExponentialHeightFogComponent.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/SpotLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture.h"
#include "Engine/TextureRenderTarget2D.h"
#include "FuryTypes.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	/** Blender metres (Z up, +Y away from the camera side) to Unreal centimetres. */
	FVector FromBlender(const TArray<TSharedPtr<FJsonValue>>& Values)
	{
		if (Values.Num() < 3)
		{
			return FVector::ZeroVector;
		}
		return FVector(Values[0]->AsNumber() * 100.0, -Values[1]->AsNumber() * 100.0, Values[2]->AsNumber() * 100.0);
	}

	template <typename T>
	T* LoadFury(const FString& Path)
	{
		return LoadObject<T>(nullptr, *Path, nullptr, LOAD_NoWarn | LOAD_Quiet);
	}
}

AFuryStadium::AFuryStadium()
{
	PrimaryActorTick.bCanEverTick = false;
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
}

UTexture* AFuryStadium::LoadTexture(const FString& Name) const
{
	return LoadFury<UTexture>(FString::Printf(TEXT("/Game/Fury/Textures/%s.%s"), *Name, *Name));
}

UMaterialInstanceDynamic* AFuryStadium::Surface(const FLinearColor& Color, float Roughness, float Metallic, float Detail, float Grime, float Tiling)
{
	if (!SurfaceBase)
	{
		return nullptr;
	}
	UMaterialInstanceDynamic* Mid = UMaterialInstanceDynamic::Create(SurfaceBase, this);
	Mid->SetVectorParameterValue(TEXT("Color"), Color);
	Mid->SetScalarParameterValue(TEXT("Roughness"), Roughness);
	Mid->SetScalarParameterValue(TEXT("Metallic"), Metallic);
	Mid->SetScalarParameterValue(TEXT("Detail"), Detail);
	Mid->SetScalarParameterValue(TEXT("Grime"), Grime);
	Mid->SetScalarParameterValue(TEXT("Tiling"), Tiling);
	Materials.Add(Mid);
	return Mid;
}

UStaticMeshComponent* AFuryStadium::AddMesh(const TCHAR* MeshName, const FVector& Location, float YawDegrees)
{
	UStaticMesh* Mesh = LoadFury<UStaticMesh>(FString::Printf(TEXT("/Game/Fury/Stadium/%s.%s"), MeshName, MeshName));
	if (!Mesh)
	{
		return nullptr;
	}
	UStaticMeshComponent* Component = NewObject<UStaticMeshComponent>(this);
	Component->SetMobility(EComponentMobility::Movable);
	Component->SetStaticMesh(Mesh);
	Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Component->SetupAttachment(GetRootComponent());
	Component->SetRelativeLocationAndRotation(Location, FRotator(0.f, YawDegrees, 0.f));
	Component->RegisterComponent();
	ApplySlotMaterials(Component);
	Props.Add(Component);
	return Component;
}

void AFuryStadium::ApplySlotMaterials(UStaticMeshComponent* Component)
{
	const FLinearColor Orange(1.f, 0.32f, 0.02f);
	const TArray<FName> Slots = Component->GetMaterialSlotNames();
	for (int32 i = 0; i < Slots.Num(); ++i)
	{
		const FString S = Slots[i].ToString();
		UMaterialInterface* Material = nullptr;
		if (S == TEXT("Concrete")) { Material = Surface(FLinearColor(0.36f, 0.36f, 0.37f), 0.86f, 0.f, 0.7f, 0.55f, 1.f); }
		else if (S == TEXT("ConcreteDark")) { Material = Surface(FLinearColor(0.045f, 0.045f, 0.05f), 0.9f, 0.f, 0.5f, 0.3f, 1.f); }
		else if (S == TEXT("SeatA")) { Material = SeatA; }
		else if (S == TEXT("SeatB")) { Material = SeatB; }
		else if (S == TEXT("Steel")) { Material = Surface(FLinearColor(0.3f, 0.32f, 0.35f), 0.42f, 0.9f); }
		else if (S == TEXT("Glass")) { Material = Surface(FLinearColor(0.012f, 0.02f, 0.035f), 0.08f, 0.7f); }
		else if (S == TEXT("WallPad")) { Material = WallPad; }
		else if (S == TEXT("LampHousing")) { Material = Surface(FLinearColor(0.04f, 0.04f, 0.045f), 0.5f, 0.7f); }
		else if (S == TEXT("Apron")) { Material = Surface(FLinearColor(0.05f, 0.075f, 0.055f), 0.92f, 0.f, 0.4f, 0.4f, 2.f); }
		else if (S == TEXT("Roof")) { Material = Surface(FLinearColor(0.07f, 0.075f, 0.085f), 0.5f, 0.6f); }
		else if (S == TEXT("GoalYellow")) { Material = Surface(FLinearColor(0.95f, 0.72f, 0.03f), 0.35f, 0.2f); }
		else if (S == TEXT("GoalPad")) { Material = GoalPad; }
		else if (S == TEXT("Leather"))
		{
			UMaterialInstanceDynamic* Mid = Surface(FLinearColor(0.25f, 0.095f, 0.04f), 0.5f, 0.f, 0.9f, 0.f, 3.f);
			if (Mid) { Mid->SetTextureParameterValue(TEXT("DetailNormal"), LoadTexture(TEXT("T_Leather_N"))); }
			Material = Mid;
		}
		else if (S == TEXT("Laces") || S == TEXT("BallStripe")) { Material = Surface(FLinearColor(0.9f, 0.9f, 0.88f), 0.6f); }
		else if (S == TEXT("Tee") || S == TEXT("CoolerBody") || S == TEXT("MarkerOrange")) { Material = Surface(Orange, 0.45f); }
		else if (S == TEXT("Pylon"))
		{
			UMaterialInstanceDynamic* Mid = Surface(Orange, 0.5f);
			if (Mid) { Mid->SetVectorParameterValue(TEXT("GlowColor"), Orange); Mid->SetScalarParameterValue(TEXT("Glow"), 0.6f); }
			Material = Mid;
		}
		else if (S == TEXT("BenchSeat")) { Material = Surface(FLinearColor(0.07f, 0.075f, 0.09f), 0.6f); }
		else if (S == TEXT("DownFace")) { Material = Surface(FLinearColor(0.02f, 0.02f, 0.02f), 0.5f); }
		else if (S == TEXT("CameraBody")) { Material = Surface(FLinearColor(0.03f, 0.03f, 0.035f), 0.4f, 0.3f); }
		else if (S == TEXT("AdBoard")) { Material = LoadFury<UMaterialInterface>(TEXT("/Game/Fury/Materials/M_Ads.M_Ads")); }
		else if (S == TEXT("Lamp") && GlowBase)
		{
			UMaterialInstanceDynamic* Mid = UMaterialInstanceDynamic::Create(GlowBase, this);
			Mid->SetVectorParameterValue(TEXT("Color"), FLinearColor(1.f, 0.97f, 0.9f));
			Mid->SetScalarParameterValue(TEXT("Brightness"), 45.f);
			Materials.Add(Mid);
			Material = Mid;
		}
		else if ((S == TEXT("Screen") || S == TEXT("ScreenSmall")) && GlowBase)
		{
			UMaterialInstanceDynamic* Mid = UMaterialInstanceDynamic::Create(GlowBase, this);
			Mid->SetTextureParameterValue(TEXT("Image"), Board);
			Mid->SetScalarParameterValue(TEXT("UseImage"), 1.f);
			Mid->SetScalarParameterValue(TEXT("Brightness"), 2.2f);
			Materials.Add(Mid);
			Material = Mid;
		}
		if (Material)
		{
			Component->SetMaterial(i, Material);
		}
	}
}

void AFuryStadium::PrepareMaterials()
{
	if (!SurfaceBase)
	{
		SurfaceBase = LoadFury<UMaterialInterface>(TEXT("/Game/Fury/Materials/M_Surface.M_Surface"));
		GlowBase = LoadFury<UMaterialInterface>(TEXT("/Game/Fury/Materials/M_Glow.M_Glow"));
	}
}

void AFuryStadium::Build()
{
	if (bBuilt)
	{
		return;
	}
	bBuilt = true;
	PrepareMaterials();

	// The video board shows whatever the HUD draws into this target.
	Board = NewObject<UTextureRenderTarget2D>(this);
	Board->RenderTargetFormat = RTF_RGBA8_SRGB;
	Board->ClearColor = FLinearColor(0.01f, 0.012f, 0.02f);
	Board->InitAutoFormat(1280, 720);
	Board->UpdateResourceImmediate(true);

	// Team-coloured surfaces are shared so Dress() can repaint them all at once.
	SeatA = Surface(FLinearColor(0.2f, 0.02f, 0.03f), 0.6f);
	SeatB = Surface(FLinearColor(0.03f, 0.04f, 0.08f), 0.6f);
	WallPad = Surface(FLinearColor(0.02f, 0.05f, 0.14f), 0.55f);
	GoalPad = Surface(FLinearColor(0.3f, 0.02f, 0.02f), 0.6f);

	// Turf: one plane, 128 m x 64 m, painted by M_Field.
	if (UStaticMesh* Plane = LoadFury<UStaticMesh>(TEXT("/Engine/BasicShapes/Plane.Plane")))
	{
		Field = NewObject<UStaticMeshComponent>(this);
		Field->SetMobility(EComponentMobility::Movable);
		Field->SetStaticMesh(Plane);
		Field->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Field->SetupAttachment(GetRootComponent());
		Field->SetRelativeScale3D(FVector(128.f, 64.f, 1.f));
		Field->SetCastShadow(false);
		Field->RegisterComponent();
		if (UMaterialInterface* Base = LoadFury<UMaterialInterface>(TEXT("/Game/Fury/Materials/M_Field.M_Field")))
		{
			FieldMaterial = UMaterialInstanceDynamic::Create(Base, this);
			Field->SetMaterial(0, FieldMaterial);
		}
	}

	// The bowl.
	if (UStaticMesh* Mesh = LoadFury<UStaticMesh>(TEXT("/Game/Fury/Stadium/SM_Stadium.SM_Stadium")))
	{
		Bowl = NewObject<UStaticMeshComponent>(this);
		Bowl->SetMobility(EComponentMobility::Movable);
		Bowl->SetStaticMesh(Mesh);
		Bowl->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Bowl->SetupAttachment(GetRootComponent());
		Bowl->RegisterComponent();
		ApplySlotMaterials(Bowl);
	}

	// Night sky: a huge inward-facing sphere.
	if (UStaticMesh* Sphere = LoadFury<UStaticMesh>(TEXT("/Engine/BasicShapes/Sphere.Sphere")))
	{
		SkyDome = NewObject<UStaticMeshComponent>(this);
		SkyDome->SetMobility(EComponentMobility::Movable);
		SkyDome->SetStaticMesh(Sphere);
		SkyDome->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		SkyDome->SetupAttachment(GetRootComponent());
		SkyDome->SetRelativeScale3D(FVector(9000.f));
		SkyDome->SetCastShadow(false);
		SkyDome->RegisterComponent();
		if (UMaterialInterface* SkyBase = LoadFury<UMaterialInterface>(TEXT("/Game/Fury/Materials/M_Sky.M_Sky")))
		{
			UMaterialInstanceDynamic* Mid = UMaterialInstanceDynamic::Create(SkyBase, this);
			Mid->SetScalarParameterValue(TEXT("Brightness"), 0.55f);
			Materials.Add(Mid);
			SkyDome->SetMaterial(0, Mid);
		}
	}

	TSharedPtr<FJsonObject> Meta;
	FString Text;
	if (FFileHelper::LoadFileToString(Text, *(FPaths::ProjectContentDir() / TEXT("Data/stadium_meta.json"))))
	{
		const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Text);
		FJsonSerializer::Deserialize(Reader, Meta);
	}
	if (Meta.IsValid())
	{
		const TSharedPtr<FJsonObject>* Screen = nullptr;
		const TArray<TSharedPtr<FJsonValue>>* Centre = nullptr;
		if (Meta->TryGetObjectField(TEXT("screen"), Screen) && (*Screen)->TryGetArrayField(TEXT("center"), Centre))
		{
			BoardWorld = FromBlender(*Centre);
		}
	}
	BuildProps(Meta);
	BuildCrowd();
	BuildLights(Meta);

	// Ambient light from the sky dome, and a touch of haze for the floodlights to shine through.
	SkyLight = NewObject<USkyLightComponent>(this);
	SkyLight->SetMobility(EComponentMobility::Movable);
	SkyLight->SetupAttachment(GetRootComponent());
	SkyLight->bRealTimeCapture = false;
	float SkyIntensity = 1.f;
	FParse::Value(FCommandLine::Get(), TEXT("FurySky="), SkyIntensity);
	SkyLight->SetIntensity(SkyIntensity);
	SkyLight->RegisterComponent();

	Fog = NewObject<UExponentialHeightFogComponent>(this);
	Fog->SetupAttachment(GetRootComponent());
	Fog->SetRelativeLocation(FVector(0.f, 0.f, 200.f));
	float FogDensity = 0.0045f;
	FParse::Value(FCommandLine::Get(), TEXT("FuryFog="), FogDensity);
	Fog->SetFogDensity(FogDensity);
	Fog->SetFogHeightFalloff(0.06f);
	Fog->SetFogInscatteringColor(FLinearColor(0.035f, 0.045f, 0.07f));
	Fog->SetVolumetricFog(false);
	Fog->SetVolumetricFogScatteringDistribution(0.55f);
	Fog->SetVolumetricFogExtinctionScale(1.2f);
	Fog->RegisterComponent();
}

void AFuryStadium::BuildProps(const TSharedPtr<FJsonObject>& Meta)
{
	const TSharedPtr<FJsonObject>* Suggested = nullptr;
	if (!Meta.IsValid() || !Meta->TryGetObjectField(TEXT("suggested_props"), Suggested))
	{
		// No metadata: at least stand the goalposts up.
		AddMesh(TEXT("SM_Goalpost"), FVector(Fury::EndLineX, 0.f, 0.f), 0.f);
		AddMesh(TEXT("SM_Goalpost"), FVector(-Fury::EndLineX, 0.f, 0.f), 180.f);
		return;
	}
	for (const auto& Pair : (*Suggested)->Values)
	{
		if (Pair.Key == TEXT("SM_KickTee"))
		{
			continue;      // the game places the tee itself
		}
		const TArray<TSharedPtr<FJsonValue>>* Entries = nullptr;
		if (!Pair.Value->TryGetArray(Entries))
		{
			continue;
		}
		for (const TSharedPtr<FJsonValue>& Entry : *Entries)
		{
			const TSharedPtr<FJsonObject> Object = Entry->AsObject();
			const TArray<TSharedPtr<FJsonValue>>* Pos = nullptr;
			if (!Object.IsValid() || !Object->TryGetArrayField(TEXT("pos"), Pos))
			{
				continue;
			}
			// A Blender yaw turns the other way once Y is mirrored.
			const float Yaw = -FMath::RadiansToDegrees(static_cast<float>(Object->GetNumberField(TEXT("yaw"))));
			UStaticMeshComponent* Prop = AddMesh(*Pair.Key, FromBlender(*Pos), Yaw);
			if (Prop && Pair.Key == TEXT("SM_ChainPole")) { ChainPoles.Add(Prop); Prop->SetVisibility(false); }
			if (Prop && Pair.Key == TEXT("SM_DownBox"))
			{
				DownBox = Prop;
				Prop->SetVisibility(false);
				const int32 Slot = Prop->GetMaterialIndex(TEXT("DownFace"));
				if (Slot != INDEX_NONE && GlowBase)
				{
					DownFace = Prop->CreateDynamicMaterialInstance(Slot, GlowBase);
					DownFace->SetScalarParameterValue(TEXT("UseImage"), 1.f);
					DownFace->SetScalarParameterValue(TEXT("Brightness"), 1.15f);
					for (int32 Down = 1; Down <= 4; ++Down) { DownDigits.Add(LoadTexture(FString::Printf(TEXT("T_Down_%d"), Down))); }
				}
			}
		}
	}
}

void AFuryStadium::SetChains(int32 Down, float Line, float Target, float Direction, bool bGoalToGo)
{
	if (Down == ShownDown && (Down == 0 || (Line == ShownLine && Target == ShownTarget && Direction == ShownDirection && bGoalToGo == bShownGoal))) { return; }
	ShownDown = Down;
	ShownLine = Line;
	ShownTarget = Target;
	ShownDirection = Direction;
	bShownGoal = bGoalToGo;
	if (DownBox)
	{
		DownBox->SetVisibility(Down > 0);
		DownBox->SetRelativeLocation(FVector(Line, -Fury::SidelineY - 145.f, 0.f));
		if (DownFace && DownDigits.IsValidIndex(Down - 1)) { DownFace->SetTextureParameterValue(TEXT("Image"), DownDigits[Down - 1]); }
	}
	for (int32 i = 0; i < ChainPoles.Num(); ++i)
	{
		ChainPoles[i]->SetVisibility(Down > 0 && !bGoalToGo);
		ChainPoles[i]->SetRelativeLocation(FVector(i == 0 ? Target - Direction * 30.f * Fury::Yard : Target, -Fury::SidelineY - 88.f, 0.f));
	}
}

void AFuryStadium::BuildCrowd()
{
	TArray<uint8> Bytes;
	if (!FFileHelper::LoadFileToArray(Bytes, *(FPaths::ProjectContentDir() / TEXT("Data/crowd.bin")), FILEREAD_Silent) || Bytes.Num() < 4)
	{
		UE_LOG(LogFury, Warning, TEXT("Stadium: no crowd data"));
		return;
	}
	int32 Count = 0;
	FMemory::Memcpy(&Count, Bytes.GetData(), 4);
	Count = FMath::Min(Count, (Bytes.Num() - 4) / 20);

	UMaterialInterface* Base = LoadFury<UMaterialInterface>(TEXT("/Game/Fury/Materials/M_Crowd.M_Crowd"));
	if (Base)
	{
		CrowdMaterial = UMaterialInstanceDynamic::Create(Base, this);
	}
	static const TCHAR* MeshNames[3] = { TEXT("SM_CrowdA"), TEXT("SM_CrowdB"), TEXT("SM_CrowdC") };
	TArray<FTransform> Transforms[3];
	TArray<float> Sections[3];
	FRandomStream Random(20261117);
	const float* Records = reinterpret_cast<const float*>(Bytes.GetData() + 4);
	for (int32 i = 0; i < Count; ++i)
	{
		const float* R = Records + i * 5;
		if (Random.FRand() < 0.06f)
		{
			continue;      // a few empty seats
		}
		const float Roll = Random.FRand();
		const int32 Kind = Roll < 0.58f ? 0 : Roll < 0.85f ? 1 : 2;      // seated, standing, arms up
		const FVector Location(R[0] * 100.f, -R[1] * 100.f, R[2] * 100.f);
		const float Yaw = -FMath::RadiansToDegrees(R[3]) + Random.FRandRange(-9.f, 9.f);
		const float Size = Random.FRandRange(0.92f, 1.08f);
		Transforms[Kind].Add(FTransform(FRotator(0.f, Yaw, 0.f), Location, FVector(Size)));
		Sections[Kind].Add(R[4]);
		if ((i & 7) == 0)
		{
			Seats.Add(Location + FVector(0.f, 0.f, 110.f));
		}
	}
	int32 Total = 0;
	for (int32 Kind = 0; Kind < 3; ++Kind)
	{
		UStaticMesh* Mesh = LoadFury<UStaticMesh>(FString::Printf(TEXT("/Game/Fury/Stadium/%s.%s"), MeshNames[Kind], MeshNames[Kind]));
		if (!Mesh || Transforms[Kind].Num() == 0)
		{
			continue;
		}
		UHierarchicalInstancedStaticMeshComponent* Instances = NewObject<UHierarchicalInstancedStaticMeshComponent>(this);
		Instances->bEnableDensityScaling = true;
		Instances->UpdateDensityScaling();
		Instances->bAutoRebuildTreeOnInstanceChanges = false;
		Instances->SetMobility(EComponentMobility::Movable);
		Instances->SetStaticMesh(Mesh);
		Instances->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Instances->SetCastShadow(false);
		Instances->bAffectDynamicIndirectLighting = false;
		Instances->bAffectDistanceFieldLighting = false;
		Instances->SetNumCustomDataFloats(1);
		Instances->SetupAttachment(GetRootComponent());
		if (CrowdMaterial)
		{
			Instances->SetMaterial(0, CrowdMaterial);
		}
		Instances->RegisterComponent();
		Instances->AddInstances(Transforms[Kind], false, false, false);
		for (int32 i = 0; i < Sections[Kind].Num(); ++i)
		{
			Instances->SetCustomDataValue(i, 0, Sections[Kind][i], false);
		}
		Instances->BuildTreeIfOutdated(false, true);
		Instances->MarkRenderStateDirty();
		Crowd.Add(Instances);
		Total += Transforms[Kind].Num();
	}
	UE_LOG(LogFury, Log, TEXT("Stadium: %d spectators seated"), Total);
}

void AFuryStadium::SetLightingQuality(int32 Level)
{
	const int32 ShadowBanks[] = {0, 1, 2, 4};
	for (int32 i = 0; i < Lights.Num(); ++i) { Lights[i]->SetCastShadows(i < ShadowBanks[Level]); }
	if (Fog) { Fog->SetVolumetricFog(Level == 3); }
}

void AFuryStadium::BuildLights(const TSharedPtr<FJsonObject>& Meta)
{
	struct FBank { FVector Pos, Aim; };
	TArray<FBank> Banks;
	const TArray<TSharedPtr<FJsonValue>>* Entries = nullptr;
	if (Meta.IsValid() && Meta->TryGetArrayField(TEXT("lights"), Entries))
	{
		for (const TSharedPtr<FJsonValue>& Entry : *Entries)
		{
			const TSharedPtr<FJsonObject> Object = Entry->AsObject();
			const TArray<TSharedPtr<FJsonValue>>* Pos = nullptr;
			const TArray<TSharedPtr<FJsonValue>>* Aim = nullptr;
			if (Object.IsValid() && Object->TryGetArrayField(TEXT("pos"), Pos) && Object->TryGetArrayField(TEXT("aim"), Aim))
			{
				Banks.Add({ FromBlender(*Pos), FromBlender(*Aim) });
			}
		}
	}
	if (Banks.Num() == 0)
	{
		for (const float X : { -4000.f, 4000.f })
		{
			for (const float Y : { -6000.f, 6000.f })
			{
				Banks.Add({ FVector(X, Y, 4200.f), FVector(X * 0.4f, 0.f, 0.f) });
			}
		}
	}
	// Tuning overrides for look development: -FuryLight=<candelas> -FurySky=<intensity> -FuryFog=<density>
	float Candelas = 11000.f;
	FParse::Value(FCommandLine::Get(), TEXT("FuryLight="), Candelas);
	for (int32 i = 0; i < Banks.Num(); ++i)
	{
		USpotLightComponent* Light = NewObject<USpotLightComponent>(this);
		Light->SetMobility(EComponentMobility::Movable);
		Light->SetupAttachment(GetRootComponent());
		Light->SetRelativeLocationAndRotation(Banks[i].Pos, (Banks[i].Aim - Banks[i].Pos).Rotation());
		Light->SetIntensityUnits(ELightUnits::Candelas);
		Light->SetIntensity(Candelas);
		Light->SetLightColor(FLinearColor(1.f, 0.97f, 0.92f));
		Light->SetAttenuationRadius(26000.f);
		Light->SetInnerConeAngle(38.f);
		Light->SetOuterConeAngle(62.f);
		Light->SetSourceRadius(350.f);
		Light->SetSoftSourceRadius(350.f);
		// One key bank casts the long turf shadows. The other banks light the far side and uniforms.
		Light->SetCastShadows(i == 0);
		Light->SetVolumetricScatteringIntensity(i < 4 ? 1.4f : 0.6f);
		Light->RegisterComponent();
		Lights.Add(Light);
	}
}

void AFuryStadium::Dress(const FFuryTeam& Home, const FFuryTeam& Away)
{
	Build();
	if (FieldMaterial)
	{
		// The home side defends the left end zone; its emblem sits at midfield.
		FieldMaterial->SetTextureParameterValue(TEXT("EndZoneLeft"), LoadTexture(TEXT("T_EndZone_") + Home.Id));
		FieldMaterial->SetTextureParameterValue(TEXT("EndZoneRight"), LoadTexture(TEXT("T_EndZone_") + Away.Id));
		FieldMaterial->SetTextureParameterValue(TEXT("MidLogo"), LoadTexture(TEXT("T_Logo_") + Home.Id));
	}
	auto Dim = [](const FLinearColor& C, float Scale) { return FLinearColor(C.R * Scale, C.G * Scale, C.B * Scale); };
	if (SeatA) { SeatA->SetVectorParameterValue(TEXT("Color"), Dim(Home.Primary, 0.45f)); }
	if (SeatB) { SeatB->SetVectorParameterValue(TEXT("Color"), Dim(Home.Secondary, 0.25f)); }
	if (WallPad) { WallPad->SetVectorParameterValue(TEXT("Color"), Dim(Home.Primary, 0.6f)); }
	if (GoalPad) { GoalPad->SetVectorParameterValue(TEXT("Color"), Dim(Home.Primary, 0.8f)); }
	if (CrowdMaterial)
	{
		// A home crowd: both seat sections lean toward the home colours, the "away" blocks only partly.
		CrowdMaterial->SetVectorParameterValue(TEXT("HomeColor"), Dim(Home.Primary, 0.9f));
		CrowdMaterial->SetVectorParameterValue(TEXT("AwayColor"), FMath::Lerp(Dim(Home.Secondary, 0.8f), Dim(Away.Primary, 0.9f), 0.35f));
	}
}

void AFuryStadium::SetExcitement(float Value)
{
	if (CrowdMaterial)
	{
		CrowdMaterial->SetScalarParameterValue(TEXT("Excitement"), FMath::Clamp(Value, 0.f, 1.f));
	}
}
