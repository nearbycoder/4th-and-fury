#include "FuryAthlete.h"
#include "TwoBoneIK.h"

#include "Components/PoseableMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

namespace
{
	// Blender's "front" (-Y) arrives in Unreal as +Y; the actor's forward is +X.
	constexpr float MeshYawOffset = -90.f;

	float SmoothStep01(float T)
	{
		T = FMath::Clamp(T, 0.f, 1.f);
		return T * T * (3.f - 2.f * T);
	}
}

AFuryAthlete::AFuryAthlete()
{
	PrimaryActorTick.bCanEverTick = false;
	USceneComponent* Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(Root);

	Mesh = CreateDefaultSubobject<UPoseableMeshComponent>(TEXT("Mesh"));
	Mesh->SetupAttachment(Root);
	Mesh->SetRelativeRotation(FRotator(0.f, MeshYawOffset, 0.f));
	Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Mesh->SetGenerateOverlapEvents(false);
	Mesh->bReceivesDecals = false;
	Mesh->SetCastShadow(true);
	Mesh->bCastDynamicShadow = true;
	// The pose can reach far from the reference pose (dives, flips); keep the bounds generous.
	Mesh->SetBoundsScale(2.5f);
	Mesh->PrimaryComponentTick.bCanEverTick = false;
}

void AFuryAthlete::Setup(const FFuryAnimSet* InAnims, USkeletalMesh* LeanMesh, USkeletalMesh* MidMesh, USkeletalMesh* BigMesh, UMaterialInterface* BodyMaterial)
{
	Anims = InAnims;
	Meshes[0] = LeanMesh ? LeanMesh : MidMesh;
	Meshes[1] = MidMesh;
	Meshes[2] = BigMesh ? BigMesh : MidMesh;
	BaseMaterial = BodyMaterial;
	if (Anims)
	{
		Current = Anims->RefPose;
		From = Anims->RefPose;
	}
}

void AFuryAthlete::SetLook(const FFuryLook& Look)
{
	USkeletalMesh* Wanted = Meshes[static_cast<int32>(Look.Build)];
	if (!Wanted)
	{
		return;
	}
	if (Mesh->GetSkinnedAsset() != Wanted)
	{
		Mesh->SetSkinnedAssetAndUpdate(Wanted, true);
		Materials.Reset();
	}
	Mesh->SetRelativeScale3D(FVector(Look.Scale));
	// Every build shares one set of animations, made on the mid build. The big build's chest is
	// wider, so its arms are carried a little further out to keep them from sinking into it.
	ArmSpread = Look.Build == EFuryBuild::Big ? FMath::DegreesToRadians(7.f) : 0.f;
	float TestSpread = 0.f;
	if (FParse::Value(FCommandLine::Get(), TEXT("FuryArmSpread="), TestSpread))
	{
		ArmSpread = FMath::DegreesToRadians(TestSpread);
	}
	bGlowing = false;

	if (!BaseMaterial)
	{
		return;
	}
	const TArray<FName> Slots = Mesh->GetMaterialSlotNames();
	if (Materials.Num() != Slots.Num())
	{
		Materials.SetNum(Slots.Num());
		for (int32 i = 0; i < Slots.Num(); ++i)
		{
			Materials[i] = UMaterialInstanceDynamic::Create(BaseMaterial, this);
			Mesh->SetMaterial(i, Materials[i]);
		}
	}

	struct FSurface { FLinearColor Color; float Roughness; float Metallic; float Number; float Fabric; float Emissive; };
	auto SurfaceFor = [&Look](const FName Slot) -> FSurface
	{
		const FString S = Slot.ToString();
		if (S == TEXT("Helmet")) return { Look.Helmet, 0.16f, 0.f, 0.f, 0.f, 0.f };
		if (S == TEXT("HelmetStripe")) return { Look.HelmetStripe, 0.2f, 0.f, 0.f, 0.f, 0.f };
		if (S == TEXT("HelmetLogo")) return { Look.Helmet, 0.16f, 0.f, 0.f, 0.f, 0.f };      // the emblem's clear parts are helmet paint
		if (S == TEXT("Facemask")) return { Look.Facemask, 0.3f, 0.85f, 0.f, 0.f, 0.f };
		if (S == TEXT("Visor")) return { FLinearColor(0.01f, 0.012f, 0.016f), 0.06f, 0.9f, 0.f, 0.f, 0.f };
		if (S == TEXT("Strap")) return { FLinearColor(0.85f, 0.85f, 0.85f), 0.6f, 0.f, 0.f, 0.f, 0.f };
		if (S == TEXT("Skin")) return { Look.Skin, 0.55f, 0.f, 0.f, 0.f, 0.f };
		if (S == TEXT("Eyes")) return { FLinearColor(0.015f, 0.012f, 0.01f), 0.4f, 0.f, 0.f, 0.f, 0.f };
		if (S == TEXT("Jersey")) return { Look.Jersey, 0.72f, 0.f, 1.f, 1.f, 0.f };
		if (S == TEXT("JerseyTrim")) return { Look.JerseyTrim, 0.7f, 0.f, 0.f, 1.f, 0.f };
		if (S == TEXT("Pants")) return { Look.Pants, 0.62f, 0.f, 0.f, 0.6f, 0.f };
		if (S == TEXT("PantsStripe")) return { Look.PantsStripe, 0.62f, 0.f, 0.f, 0.6f, 0.f };
		if (S == TEXT("Belt")) return { FLinearColor(0.03f, 0.03f, 0.03f), 0.5f, 0.f, 0.f, 0.f, 0.f };
		if (S == TEXT("Socks")) return { Look.Socks, 0.8f, 0.f, 0.f, 1.f, 0.f };
		if (S == TEXT("Shoes")) return { Look.Shoes, 0.35f, 0.f, 0.f, 0.f, 0.f };
		if (S == TEXT("ShoeSole")) return { FLinearColor(0.75f, 0.75f, 0.75f), 0.6f, 0.f, 0.f, 0.f, 0.f };
		if (S == TEXT("Gloves")) return { Look.Gloves, 0.55f, 0.f, 0.f, 0.3f, 0.f };
		if (S == TEXT("Bands")) return { Look.JerseyTrim, 0.75f, 0.f, 0.f, 1.f, 0.f };
		return { FLinearColor(0.5f, 0.5f, 0.5f), 0.6f, 0.f, 0.f, 0.f, 0.f };
	};

	for (int32 i = 0; i < Slots.Num(); ++i)
	{
		UMaterialInstanceDynamic* Mid = Materials[i];
		if (!Mid)
		{
			continue;
		}
		const FSurface Surface = SurfaceFor(Slots[i]);
		Mid->SetVectorParameterValue(TEXT("Color"), Surface.Color);
		Mid->SetScalarParameterValue(TEXT("Roughness"), Surface.Roughness);
		Mid->SetScalarParameterValue(TEXT("Metallic"), Surface.Metallic);
		Mid->SetScalarParameterValue(TEXT("UseNumber"), Surface.Number);
		Mid->SetScalarParameterValue(TEXT("Fabric"), Surface.Fabric);
		Mid->SetScalarParameterValue(TEXT("Number"), static_cast<float>(FMath::Clamp(Look.Number, 0, 99)));
		Mid->SetVectorParameterValue(TEXT("NumberFill"), Look.NumberFill);
		Mid->SetVectorParameterValue(TEXT("NumberEdge"), Look.NumberEdge);
		if (Slots[i] == TEXT("HelmetLogo") && Look.Logo)
		{
			Mid->SetTextureParameterValue(TEXT("Logo"), Look.Logo);
			Mid->SetScalarParameterValue(TEXT("UseLogo"), 1.f);
		}
		if (Slots[i] == TEXT("Visor"))
		{
			for (int32 LOD = 0; LOD < Wanted->GetLODNum(); ++LOD)
			{
				Mesh->ShowMaterialSection(i, INDEX_NONE, Look.bVisor, LOD);
			}
		}
	}
}

const FFuryClip* AFuryAthlete::StanceFor(const FFuryAthleteState& State) const
{
	if (State.bPasser)
	{
		return Anims->FindFirst({ TEXT("QBSet"), TEXT("Idle") });
	}
	switch (static_cast<EFuryStance>(State.Variant))
	{
	case EFuryStance::Ready: return Anims->FindFirst({ TEXT("Ready"), TEXT("Idle") });
	case EFuryStance::ThreePoint: return Anims->FindFirst({ TEXT("Stance3"), TEXT("Ready"), TEXT("Idle") });
	case EFuryStance::Center: return Anims->FindFirst({ TEXT("StanceCenter"), TEXT("Stance3"), TEXT("Idle") });
	case EFuryStance::QB: return Anims->FindFirst({ TEXT("StanceQB"), TEXT("Ready"), TEXT("Idle") });
	case EFuryStance::QBSet: return Anims->FindFirst({ TEXT("QBSet"), TEXT("Idle") });
	default: return Anims->FindFirst({ TEXT("Idle") });
	}
}

AFuryAthlete::FLayer AFuryAthlete::ActionFor(const FFuryAthleteState& State) const
{
	const bool bMoving = State.Vel.SizeSquared() > 200.f * 200.f;
	const uint8 V = State.Variant;
	switch (State.Act)
	{
	case EFuryAct::Snap: return { Anims->FindFirst({ TEXT("Snap") }) };
	case EFuryAct::CatchSnap: return { Anims->FindFirst({ TEXT("CatchSnap") }) };
	case EFuryAct::Throw: return { Anims->FindFirst({ TEXT("Throw") }), bMoving };
	case EFuryAct::Handoff: return { Anims->FindFirst({ TEXT("Handoff") }), true };
	case EFuryAct::Catch: return V == 1 ? FLayer{ Anims->FindFirst({ TEXT("CatchHigh"), TEXT("CatchChest") }) } : FLayer{ Anims->FindFirst({ TEXT("CatchChest") }), true };
	case EFuryAct::Swat: return { Anims->FindFirst({ TEXT("Swat"), TEXT("CatchHigh") }) };
	case EFuryAct::Block: return { Anims->FindFirst({ TEXT("BlockLoop"), TEXT("Ready") }) };
	case EFuryAct::Dive: return { Anims->FindFirst({ TEXT("DiveTackle"), TEXT("HitFront") }) };
	case EFuryAct::Tackle: return { Anims->FindFirst({ TEXT("TackleWrap"), TEXT("DiveTackle") }) };
	case EFuryAct::BigHit: return { Anims->FindFirst({ TEXT("BigHit"), TEXT("Shove") }) };
	case EFuryAct::Shove: return { Anims->FindFirst({ TEXT("Shove"), TEXT("BigHit") }) };
	case EFuryAct::Hit:
		switch (static_cast<EFuryFall>(V))
		{
		case EFuryFall::Front: return { Anims->FindFirst({ TEXT("HitFront"), TEXT("HitBack") }) };
		case EFuryFall::Flip: return { Anims->FindFirst({ TEXT("HitFlip"), TEXT("HitBack") }) };
		case EFuryFall::Spin: return { Anims->FindFirst({ TEXT("HitSpin"), TEXT("HitFront"), TEXT("HitBack") }) };
		default: return { Anims->FindFirst({ TEXT("HitBack") }) };
		}
	case EFuryAct::GroundRecoil: return { V == 0 ? Anims->FindFirst({ TEXT("GroundHitBack"), TEXT("DownBack") }) : Anims->FindFirst({ TEXT("GroundHitFront"), TEXT("DownFront") }) };
	case EFuryAct::Down: return { V == 0 ? Anims->FindFirst({ TEXT("DownBack") }) : Anims->FindFirst({ TEXT("DownFront"), TEXT("DownBack") }) };
	case EFuryAct::GetUp: return { V == 0 ? Anims->FindFirst({ TEXT("GetUpBack") }) : Anims->FindFirst({ TEXT("GetUpFront"), TEXT("GetUpBack") }) };
	case EFuryAct::Stumble: return { Anims->FindFirst({ TEXT("Stumble") }) };
	case EFuryAct::StiffArm: return { Anims->FindFirst({ TEXT("StiffArm") }), false, true };
	case EFuryAct::Spin: return { Anims->FindFirst({ TEXT("Spin") }) };
	case EFuryAct::Juke: return { V == 0 ? Anims->FindFirst({ TEXT("JukeL") }) : Anims->FindFirst({ TEXT("JukeR") }) };
	case EFuryAct::Hurdle: return { Anims->FindFirst({ TEXT("Hurdle") }) };
	case EFuryAct::DiveBall: return { Anims->FindFirst({ TEXT("DiveBall"), TEXT("DiveTackle") }) };
	case EFuryAct::Kick: return { Anims->FindFirst({ TEXT("Kick") }) };
	case EFuryAct::Punt: return { Anims->FindFirst({ TEXT("Punt"), TEXT("Kick") }) };
	case EFuryAct::PickUp: return { Anims->FindFirst({ TEXT("PickUp") }), bMoving };
	case EFuryAct::Celebrate:
		return { V == 0 ? Anims->FindFirst({ TEXT("CelebSpike"), TEXT("CelebFlex") })
			: V == 1 ? Anims->FindFirst({ TEXT("CelebDance"), TEXT("CelebFlex") })
			: Anims->FindFirst({ TEXT("CelebFlex"), TEXT("CelebDance") }) };
	case EFuryAct::Dejected: return { Anims->FindFirst({ TEXT("Dejected"), TEXT("Idle") }) };
	case EFuryAct::Signal: return { Anims->FindFirst({ TEXT("Signal1st") }), true };
	case EFuryAct::ElbowDrop: return { Anims->FindFirst({ TEXT("ElbowDrop"), TEXT("DiveTackle") }) };
	default: return {};
	}
}

/**
 * The simulation decides how long an action lasts and when its key moment falls (the release of
 * a throw, the contact of a kick). The clip is stretched so its own key moment lands on the
 * simulation's, which keeps the ball leaving the hand exactly when the pass is launched.
 */
float AFuryAthlete::ClipTime(const FFuryAthleteState& State, const FFuryClip& Clip) const
{
	if (Clip.bLoop || State.ActLength <= 0.f)
	{
		return State.ActTime;
	}
	if (State.Act == EFuryAct::Dive && State.ActKey <= 0.f)
	{
		// Hold the outstretched silhouette while the collision is still open.
		// Contact sets ActKey to the impact time and continues from the clamp.
		const float Hit = Clip.Event(TEXT("hit"), Clip.Length / 3.f);
		if (State.ActTime < 0.1f) { return State.ActTime / 0.1f * Hit * 0.82f; }
		if (State.ActTime <= 0.36f) { return Hit * FMath::Lerp(0.82f, 1.f, (State.ActTime - 0.1f) / 0.26f); }
		return Hit + (Clip.Length - Hit) * (State.ActTime - 0.36f) / FMath::Max(State.ActLength - 0.36f, 0.05f);
	}
	static const FName KeyNames[] = { TEXT("release"), TEXT("catch"), TEXT("contact"), TEXT("hit"), TEXT("apex"), TEXT("grab"), TEXT("give"), TEXT("spike") };
	float Key = -1.f;
	for (const FName& Name : KeyNames)
	{
		Key = Clip.Event(Name, -1.f);
		if (Key > 0.f)
		{
			break;
		}
	}
	if (Key > 0.f && State.ActKey > 0.f)
	{
		if (State.ActTime < State.ActKey)
		{
			return State.ActTime * Key / State.ActKey;
		}
		return Key + (State.ActTime - State.ActKey) * (Clip.Length - Key) / FMath::Max(State.ActLength - State.ActKey, 0.05f);
	}
	return State.ActTime * Clip.Length / State.ActLength;
}

void AFuryAthlete::Locomotion(const FFuryAthleteState& State, float DeltaTime, FFuryPose& Out)
{
	const int32 N = Anims->NumBones;
	const float Speed = State.Vel.Size();
	const FVector2D Facing = Fury::FromAngle(State.Yaw);
	const FVector2D Right(-Facing.Y, Facing.X);

	// How much we are moving at all, and in which direction relative to where we face.
	const float MoveTarget = State.Act == EFuryAct::Stand ? 0.f : FMath::Clamp((Speed - 25.f) / 140.f, 0.f, 1.f);
	MoveBlend = Fury::Approach(MoveBlend, MoveTarget, DeltaTime * 7.f);
	if (Speed > 30.f)
	{
		const FVector2D Local(FVector2D::DotProduct(State.Vel, Facing) / Speed, FVector2D::DotProduct(State.Vel, Right) / Speed);
		DirBlend = FMath::Lerp(DirBlend, Local, FMath::Min(1.f, DeltaTime * 12.f));
	}

	const FFuryClip* Stance = StanceFor(State);
	const bool bCarry = State.bHasBall && !State.bPasser;
	const FFuryClip* Jog = Anims->FindFirst({ TEXT("Jog"), TEXT("Run") });
	const FFuryClip* Run = bCarry ? Anims->FindFirst({ TEXT("RunBall"), TEXT("Run") }) : Anims->FindFirst({ TEXT("Run"), TEXT("Jog") });
	const FFuryClip* Back = State.bPasser ? Anims->FindFirst({ TEXT("QBDrop"), TEXT("Backpedal") }) : Anims->FindFirst({ TEXT("Backpedal") });
	const FFuryClip* Left = Anims->FindFirst({ TEXT("ShuffleL") });
	const FFuryClip* RightClip = Anims->FindFirst({ TEXT("ShuffleR") });
	if (bCarry && Run)
	{
		Jog = Anims->FindFirst({ TEXT("JogBall"), TEXT("RunBall"), TEXT("Run") });
	}

	if (Stance)
	{
		Stance->Sample(State.ActTime, Out, N);
	}
	else
	{
		Out = Anims->RefPose;
	}
	Grip = State.bHasBall ? (State.bPasser ? EFuryGrip::Hand : EFuryGrip::Tuck) : EFuryGrip::None;
	if (MoveBlend <= 0.001f || !Run)
	{
		return;
	}

	// Direction weights (forward / back / left / right), sharpened so one gait dominates.
	float WF = FMath::Max(0.f, DirBlend.X), WB = FMath::Max(0.f, -DirBlend.X);
	float WR = FMath::Max(0.f, DirBlend.Y), WL = FMath::Max(0.f, -DirBlend.Y);
	if (!Back) { WF += WB; WB = 0.f; }
	if (!Left || !RightClip) { WF += WL + WR; WL = WR = 0.f; }
	WF *= WF; WB *= WB; WL *= WL; WR *= WR;
	const float Sum = FMath::Max(WF + WB + WL + WR, KINDA_SMALL_NUMBER);
	WF /= Sum; WB /= Sum; WL /= Sum; WR /= Sum;

	const float JogSpeed = Jog && Jog->Speed > 0.f ? Jog->Speed : 450.f;
	const float RunSpeed = Run->Speed > 0.f ? Run->Speed : 800.f;
	const float GaitTarget = Jog == Run ? 1.f : FMath::Clamp((Speed - JogSpeed) / FMath::Max(RunSpeed - JogSpeed, 1.f), 0.f, 1.f);
	GaitBlend = Fury::Approach(GaitBlend, GaitTarget, DeltaTime * 5.f);

	// One phase drives every gait so they stay in step; its rate keeps the feet from skating.
	auto Stride = [](const FFuryClip* Clip, float Fallback) { return Clip && Clip->Speed > 0.f ? Clip->Speed * Clip->Length : Fallback; };
	const float ForwardStride = FMath::Lerp(Stride(Jog, 300.f), Stride(Run, 430.f), GaitBlend);
	const float StrideLength = WF * ForwardStride + WB * Stride(Back, 270.f) + (WL + WR) * Stride(Left, 230.f);
	const float NextPhase = Phase + DeltaTime * Speed / (FMath::Max(StrideLength, 50.f) * Mesh->GetRelativeScale3D().Z);
	bStepped = FMath::FloorToInt(2.f * NextPhase) != FMath::FloorToInt(2.f * Phase);
	Phase = FMath::Frac(NextPhase);

	FFuryPose Moving, Temp;
	bool bHave = false;
	auto Add = [&](const FFuryClip* Clip, float Weight, float& Accumulated)
	{
		if (!Clip || Weight <= 0.001f)
		{
			return;
		}
		Clip->Sample(Phase * Clip->Length, Temp, N);
		Accumulated += Weight;
		if (!bHave)
		{
			Moving = Temp;
			bHave = true;
		}
		else
		{
			Moving.BlendTo(Temp, Weight / Accumulated, N);
		}
	};
	float Accumulated = 0.f;
	Add(Jog, WF * (1.f - GaitBlend), Accumulated);
	Add(Run, WF * GaitBlend, Accumulated);
	Add(Back, WB, Accumulated);
	Add(Left, WL, Accumulated);
	Add(RightClip, WR, Accumulated);
	if (bHave)
	{
		// The backpedal and shuffle were authored for coverage. Keep the carrying
		// arm wrapped around the ball when a runner cuts across his body.
		if (bCarry && Jog && WF < 0.99f)
		{
			Jog->Sample(Phase * Jog->Length, Temp, N);
			Moving.BlendToMasked(Temp, 1.f - WF, Anims->CarryArm, N);
		}
		Out.BlendTo(Moving, MoveBlend, N);
	}
}

void AFuryAthlete::BuildPose(const FFuryAthleteState& State, float DeltaTime, FFuryPose& Out)
{
	const int32 N = Anims->NumBones;
	const FLayer Action = ActionFor(State);
	const bool bFullBody = Action.Clip && !Action.bUpperOnly && !Action.bLeftArmOnly;

	if (bFullBody)
	{
		Action.Clip->Sample(ClipTime(State, *Action.Clip), Out, N);
		Grip = State.bHasBall ? (Action.Clip->Grip == EFuryGrip::None ? EFuryGrip::Hand : Action.Clip->Grip) : EFuryGrip::None;
		// Keep the locomotion phase ticking so the feet do not restart from zero afterwards.
		Phase = FMath::Frac(Phase + DeltaTime * 1.6f);
	}
	else
	{
		Locomotion(State, DeltaTime, Out);
		if (Action.Clip)
		{
			FFuryPose Over;
			Action.Clip->Sample(ClipTime(State, *Action.Clip), Over, N);
			const float Length = State.ActLength > 0.f ? State.ActLength : Action.Clip->Length;
			const float Envelope = FMath::Clamp(State.ActTime / 0.07f, 0.f, 1.f) * FMath::Clamp((Length - State.ActTime) / 0.12f, 0.f, 1.f);
			Out.BlendToMasked(Over, Envelope, Action.bLeftArmOnly ? Anims->LeftArm : Anims->UpperBody, N);
			if (!Action.bLeftArmOnly && State.bHasBall && Action.Clip->Grip != EFuryGrip::None)
			{
				Grip = Action.Clip->Grip;
			}
		}
	}

	// Cross-fade from whatever was on screen whenever the full-body action changes.
	const bool bChanged = bFullBody != bWasFullBody || (bFullBody && State.ActSerial != LastSerial);
	if (bChanged && bPosed)
	{
		From = Current;
		BlendTime = 0.f;
		switch (State.Act)
		{
		case EFuryAct::GroundRecoil: BlendLength = 0.015f; break;
		case EFuryAct::Hit: BlendLength = 0.032f; break;
		case EFuryAct::Tackle: BlendLength = 0.035f; break;
		case EFuryAct::Dive: case EFuryAct::BigHit: case EFuryAct::Shove: case EFuryAct::Spin: case EFuryAct::Juke: BlendLength = 0.07f; break;
		case EFuryAct::GetUp: case EFuryAct::Down: BlendLength = 0.1f; break;
		default: BlendLength = bFullBody ? 0.12f : 0.2f; break;
		}
	}
	bWasFullBody = bFullBody;
	LastSerial = State.ActSerial;
	LastAct = State.Act;

	if (BlendTime < BlendLength)
	{
		BlendTime += DeltaTime;
		const float Alpha = SmoothStep01(BlendTime / BlendLength);
		FFuryPose Mixed = From;
		Mixed.BlendTo(Out, Alpha, N);
		Out = Mixed;
	}
}

// A planted toe is a world-space pivot. Preserve the authored foot rotation while the hip moves.
void AFuryAthlete::PlantFoot(int32 Side, int32 Toe, TArray<FTransform>& Local)
{
	if (Toe == INDEX_NONE) { return; }
	const FTransform& World = Mesh->GetComponentTransform();
	const FVector ToePos = ComponentSpace[Toe].GetLocation();
	if (ToePos.Z >= 10.f) { FootAnchor[Side].Reset(); return; }
	if (!FootAnchor[Side].IsSet()) { FootAnchor[Side] = World.TransformPosition(ToePos); return; }
	FVector Drift = World.InverseTransformPosition(FootAnchor[Side].GetValue()) - ToePos;
	Drift.Z = 0.f;
	// Fade out as the foot lifts, and cap correction at a comfortable half stride.
	Drift = Drift.GetClampedToMaxSize(26.f) * SmoothStep01((10.f - ToePos.Z) / 6.f);
	const int32 Foot = Anims->Parents[Toe], Calf = Anims->Parents[Foot], Thigh = Anims->Parents[Calf];
	FTransform Hip = ComponentSpace[Thigh], Knee = ComponentSpace[Calf], Ankle = ComponentSpace[Foot];
	const FVector Target = Ankle.GetLocation() + Drift, Pole = Knee.GetLocation();
	AnimationCore::SolveTwoBoneIK(Hip, Knee, Ankle, Pole, Target, false, 1., 1.);
	Local[Thigh] = Hip.GetRelativeTransform(ComponentSpace[Anims->Parents[Thigh]]);
	Local[Calf] = Knee.GetRelativeTransform(Hip);
	Local[Foot] = Ankle.GetRelativeTransform(Knee);
}

void AFuryAthlete::Apply(const FFuryPose& Pose, bool bPlant)
{
	const int32 N = Anims->NumBones;
	TArray<FTransform>& Local = Mesh->BoneSpaceTransforms;
	if (Local.Num() < N)
	{
		return;
	}
	ComponentSpace.SetNum(N);
	for (int32 i = 0; i < N; ++i)
	{
		FQuat Rotation(Pose.Rot[i]);
		if (ArmSpread != 0.f && (i == Anims->UpperArmL || i == Anims->UpperArmR))
		{
			// About the bone's own X axis (Z would swing the arm forward and back instead).
			Rotation = Rotation * FQuat(FVector::XAxisVector, ArmSpread);
		}
		Local[i].SetComponents(Rotation, FVector(Pose.Loc[i]), FVector::OneVector);
		const int32 Parent = Anims->Parents[i];
		ComponentSpace[i] = Parent >= 0 ? Local[i] * ComponentSpace[Parent] : Local[i];
	}
	if (bPlant)
	{
		PlantFoot(0, Anims->ToeL, Local);
		PlantFoot(1, Anims->ToeR, Local);
		for (int32 i = 1; i < N; ++i)
		{
			ComponentSpace[i] = Local[i] * ComponentSpace[Anims->Parents[i]];
		}
	}
	else
	{
		FootAnchor[0].Reset();
		FootAnchor[1].Reset();
	}
	Mesh->RefreshBoneTransforms();
	Current = Pose;
	bPosed = true;
}

void AFuryAthlete::Advance(const FFuryAthleteState& State, float DeltaTime)
{
	if (!Anims || !Mesh->GetSkinnedAsset())
	{
		return;
	}
	SetActorHiddenInGame(!State.bVisible);
	SetActorLocationAndRotation(FVector(State.Pos.X, State.Pos.Y, State.Height), FRotator(0.f, FMath::RadiansToDegrees(State.Yaw), 0.f));
	if (State.bFury != bGlowing)
	{
		// In Fury the whole athlete smoulders.
		bGlowing = State.bFury;
		for (UMaterialInstanceDynamic* Mid : Materials)
		{
			if (Mid)
			{
				Mid->SetScalarParameterValue(TEXT("Glow"), bGlowing ? 2.4f : 0.f);
			}
		}
	}

	FFuryPose Pose;
	bStepped = false;
	if (State.ActSerial != LastSerial) { FootAnchor[0].Reset(); FootAnchor[1].Reset(); }
	BuildPose(State, DeltaTime, Pose);

	// Lean into turns and accelerations: a small roll of the hips, strongest at a sprint.
	const float YawRate = DeltaTime > KINDA_SMALL_NUMBER ? Fury::AngleDelta(LastYaw, State.Yaw) / DeltaTime : 0.f;
	LastYaw = State.Yaw;
	const float LeanTarget = bWasFullBody ? 0.f : FMath::Clamp(YawRate * 0.045f, -0.3f, 0.3f) * FMath::Clamp(State.Vel.Size() / 800.f, 0.f, 1.f);
	Lean = FMath::Lerp(Lean, LeanTarget, FMath::Min(1.f, DeltaTime * 8.f));
	if (Anims->Pelvis != INDEX_NONE && FMath::Abs(Lean) > 0.002f)
	{
		// Roll about the character's forward axis, expressed in the pelvis' parent (root) space.
		const FQuat4f Roll(FVector3f(0.f, 1.f, 0.f), -Lean);
		Pose.Rot[Anims->Pelvis] = Roll * Pose.Rot[Anims->Pelvis];
	}
	if (Anims->Towel != INDEX_NONE)
	{
		// A damped hinge on the loose towel hem. The waistband stays pinned to the rig.
		const float Run = FMath::Clamp(State.Vel.Size() / 850.f, 0.f, 1.f);
		const float Swing = Run * (0.16f + 0.12f * FMath::Sin(2.f * PI * Phase));
		for (float Left = FMath::Min(DeltaTime, 0.1f); Left > 0.f; Left -= 1.f/120.f)
		{
			const float Dt = FMath::Min(Left, 1.f/120.f);
			TowelVelocity += ((Swing - TowelAngle) * 165.f - TowelVelocity * 15.f) * Dt;
			TowelAngle += TowelVelocity * Dt;
		}
		Mesh->SetCustomPrimitiveDataFloat(0, FMath::Clamp(2.8f * TowelAngle, 0.f, 0.9f));
		Pose.Rot[Anims->Towel] *= FQuat4f(FVector3f::XAxisVector, TowelAngle);
	}
	const bool bRunningMove = State.Act == EFuryAct::Spin || State.Act == EFuryAct::Juke ||
		State.Act == EFuryAct::Hurdle || State.Act == EFuryAct::Stumble || State.Act == EFuryAct::Block;
	Apply(Pose, bRunningMove && State.Height < 5.f);
}

void AFuryAthlete::PreviewClip(FName ClipName, float Time)
{
	if (!Anims || !Mesh->GetSkinnedAsset())
	{
		return;
	}
	FFuryPose Pose = Anims->RefPose;
	if (const FFuryClip* Clip = Anims->Find(ClipName))
	{
		Clip->Sample(Time, Pose, Anims->NumBones);
		Grip = Clip->Grip;
	}
	Apply(Pose);
}

FTransform AFuryAthlete::BoneWorld(int32 Bone) const
{
	if (!ComponentSpace.IsValidIndex(Bone))
	{
		return GetActorTransform();
	}
	return ComponentSpace[Bone] * Mesh->GetComponentTransform();
}

FTransform AFuryAthlete::GripWorld(EFuryGrip InGrip) const
{
	const int32 Bone = InGrip == EFuryGrip::Tuck ? Anims->BallTuck : Anims->BallHand;
	if (Bone != INDEX_NONE && ComponentSpace.IsValidIndex(Bone))
	{
		// The socket's local Y is the ball's long axis; the ball mesh is long in X.
		FTransform Socket = BoneWorld(Bone);
		Socket.SetRotation(Socket.GetRotation() * FQuat(FRotator(0.f, 90.f, 0.f)));
		Socket.SetScale3D(FVector::OneVector);
		return Socket;
	}
	const int32 Hand = Anims->HandR;
	FTransform Fallback = Hand != INDEX_NONE ? BoneWorld(Hand) : GetActorTransform();
	Fallback.SetScale3D(FVector::OneVector);
	return Fallback;
}

FVector AFuryAthlete::HeadWorld() const
{
	return Anims && Anims->Head != INDEX_NONE ? BoneWorld(Anims->Head).GetLocation() : GetActorLocation() + FVector(0.f, 0.f, 170.f);
}
