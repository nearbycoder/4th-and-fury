#include "FuryFX.h"

#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/Actor.h"
#include "Materials/MaterialInterface.h"

namespace
{
	constexpr int32 CustomFloats = 4;       // RGB + brightness, read by M_Particle
	constexpr int32 MaxParticles = 5000;
}

void FFuryFX::Init(AActor* Owner)
{
	Random.Initialize(4242);
	UStaticMesh* Plane = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Plane.Plane"));
	UMaterialInterface* Material = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Fury/Materials/M_Particle.M_Particle"), nullptr, LOAD_NoWarn | LOAD_Quiet);
	if (!Owner || !Plane || !Material)
	{
		return;
	}
	UInstancedStaticMeshComponent* ISM = NewObject<UInstancedStaticMeshComponent>(Owner);
	ISM->SetMobility(EComponentMobility::Movable);
	ISM->SetStaticMesh(Plane);
	ISM->SetMaterial(0, Material);
	ISM->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	ISM->SetCanEverAffectNavigation(false);
	ISM->SetCastShadow(false);
	ISM->bAffectDynamicIndirectLighting = false;
	ISM->bAffectDistanceFieldLighting = false;
	ISM->SetNumCustomDataFloats(CustomFloats);
	ISM->SetupAttachment(Owner->GetRootComponent());
	ISM->SetUsingAbsoluteLocation(true);
	ISM->SetUsingAbsoluteRotation(true);
	ISM->SetUsingAbsoluteScale(true);
	ISM->RegisterComponent();
	Instances = ISM;
}

void FFuryFX::Clear()
{
	Particles.Reset();
}

void FFuryFX::Emit(const FVector& Origin, const FVector& Velocity, const FLinearColor& Color, float Life, float Size, float Brightness, float Gravity, float Drag, float Growth)
{
	if (Particles.Num() >= MaxParticles)
	{
		return;
	}
	FParticle& P = Particles.AddDefaulted_GetRef();
	P.P = Origin;
	P.V = Velocity;
	P.Color = Color;
	P.Life = P.MaxLife = Life;
	P.Size = Size;
	P.Growth = Growth;
	P.Brightness = Brightness;
	P.Gravity = Gravity;
	P.Drag = Drag;
}

void FFuryFX::Burst(const FVector& Origin, const FLinearColor& Color, int32 Count, float Speed, float Life, float Size, float Brightness, float Gravity, float UpBias)
{
	Count = FMath::RoundToInt(Count * ParticleDensity);
	for (int32 i = 0; i < Count; ++i)
	{
		FVector Dir = Random.VRand();
		Dir.Z = FMath::Abs(Dir.Z) * (1.f - UpBias) + UpBias;
		Emit(Origin, Dir.GetSafeNormal() * Speed * Random.FRandRange(0.35f, 1.f), Color, Life * Random.FRandRange(0.6f, 1.f), Size * Random.FRandRange(0.6f, 1.2f), Brightness, Gravity, 1.6f);
	}
}

void FFuryFX::Firework(const FVector& Origin, const FLinearColor& Color, float Scale)
{
	Emit(Origin, FVector::ZeroVector, FLinearColor::White, 0.25f, 900.f * Scale, 6.f, 0.f, 0.f, 2500.f);
	const int32 Count = FMath::RoundToInt(90 * ParticleDensity);
	for (int32 i = 0; i < Count; ++i)
	{
		const FVector Dir = Random.VRand();
		const FLinearColor Tint = FMath::Lerp(Color, FLinearColor::White, Random.FRandRange(0.f, 0.35f));
		Emit(Origin, Dir * 1500.f * Scale * Random.FRandRange(0.6f, 1.f), Tint, Random.FRandRange(1.1f, 1.9f), 70.f * Scale, 5.f, 260.f, 1.3f, -18.f);
	}
}

void FFuryFX::Flame(const FVector& Origin, const FVector& Drift)
{
	const FVector Jitter(Random.FRandRange(-22.f, 22.f), Random.FRandRange(-22.f, 22.f), Random.FRandRange(0.f, 30.f));
	const FLinearColor Color = FMath::Lerp(FLinearColor(1.f, 0.55f, 0.08f), FLinearColor(1.f, 0.16f, 0.02f), Random.FRand());
	Emit(Origin + Jitter, Drift + FVector(Random.FRandRange(-30.f, 30.f), Random.FRandRange(-30.f, 30.f), Random.FRandRange(120.f, 260.f)), Color,
		Random.FRandRange(0.28f, 0.5f), Random.FRandRange(34.f, 58.f), 2.4f, -40.f, 1.2f, -60.f);
}

void FFuryFX::Tick(float DeltaTime, const FVector& CameraForward, const FVector& CameraRight)
{
	UInstancedStaticMeshComponent* ISM = Instances.Get();
	if (!ISM || (Particles.IsEmpty() && LastUsed <= 2))
	{
		return;
	}
	// Every quad faces the camera: its normal (+Z of the plane) points back along the view direction.
	const FQuat Facing = FRotationMatrix::MakeFromZX(-CameraForward, CameraRight).ToQuat();

	Transforms.Reset();
	Data.Reset();
	// Two invisible sentinels at opposite corners keep the component's bounds over the whole arena.
	static const float Dark[CustomFloats] = { 0.f, 0.f, 0.f, 0.f };
	Transforms.Add(FTransform(FQuat::Identity, FVector(-14000.f, -11000.f, -100.f), FVector(0.001f)));
	Data.Append(Dark, CustomFloats);
	Transforms.Add(FTransform(FQuat::Identity, FVector(14000.f, 11000.f, 9000.f), FVector(0.001f)));
	Data.Append(Dark, CustomFloats);

	for (int32 i = Particles.Num() - 1; i >= 0; --i)
	{
		FParticle& P = Particles[i];
		P.Life -= DeltaTime;
		if (P.Life <= 0.f)
		{
			Particles.RemoveAtSwap(i, EAllowShrinking::No);
			continue;
		}
		P.V.Z -= P.Gravity * DeltaTime;
		P.V *= FMath::Exp(-P.Drag * DeltaTime);
		P.P += P.V * DeltaTime;
		if (P.P.Z < 4.f && P.Gravity > 0.f)
		{
			P.P.Z = 4.f;
			P.V = FVector(P.V.X * 0.5f, P.V.Y * 0.5f, FMath::Abs(P.V.Z) * 0.25f);
		}
		P.Size = FMath::Max(1.f, P.Size + P.Growth * DeltaTime);
		const float Age = P.Life / P.MaxLife;                      // 1 new .. 0 gone
		const float Fade = FMath::Min(1.f, Age * 2.2f);
		Transforms.Add(FTransform(Facing, P.P, FVector(P.Size / 100.f)));
		const float Values[CustomFloats] = { P.Color.R, P.Color.G, P.Color.B, P.Brightness * Fade };
		Data.Append(Values, CustomFloats);
	}

	// Instances used last frame but not this one are parked out of sight.
	const int32 Used = Transforms.Num();
	static const FTransform Hidden(FQuat::Identity, FVector(0.0, 0.0, -3000.0), FVector(0.0001));
	for (int32 i = Used; i < LastUsed; ++i)
	{
		Transforms.Add(Hidden);
		Data.Append(Dark, CustomFloats);
	}
	LastUsed = Used;
	const int32 Count = Transforms.Num();
	const bool bGrow = PoolSize < Count;
	if (bGrow)
	{
		const int32 Grow = FMath::Max(64, static_cast<int32>(FMath::RoundUpToPowerOfTwo(Count)) - PoolSize);
		TArray<FTransform> Extra;
		Extra.Init(Hidden, Grow);
		ISM->AddInstances(Extra, false, true, false);
		PoolSize += Grow;
	}
	ISM->BatchUpdateInstancesTransforms(0, Transforms, true, false, true);
	ISM->SetCustomData(0, Count - 1, Data, false);
	if (bGrow)
	{
		ISM->UpdateBounds();
	}
	ISM->MarkRenderInstancesDirty();
}
