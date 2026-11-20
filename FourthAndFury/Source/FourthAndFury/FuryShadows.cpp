#include "FuryShadows.h"

#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "FuryAthlete.h"
#include "Materials/MaterialInterface.h"

void FFuryShadows::Init(AActor* Owner)
{
	if (Mesh.IsValid()) { Show(true); return; }
	UStaticMesh* Quad = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Plane.Plane"));
	UMaterialInterface* Soft = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Fury/Materials/M_ContactShadow.M_ContactShadow"));
	if (!Quad || !Soft) { return; }
	UInstancedStaticMeshComponent* Component = NewObject<UInstancedStaticMeshComponent>(Owner);
	Component->SetupAttachment(Owner->GetRootComponent());
	Component->SetMobility(EComponentMobility::Movable);
	Component->SetStaticMesh(Quad);
	Component->SetMaterial(0, Soft);
	Component->SetNumCustomDataFloats(1);
	Component->SetCanEverAffectNavigation(false);
	Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Component->SetCastShadow(false);
	Component->SetTranslucentSortPriority(-1);
	Component->RegisterComponent();
	Transforms.Init(FTransform::Identity, Fury::NumPlayers * 3);
	Opacity.Init(0.f, Transforms.Num());
	Component->AddInstances(Transforms, false, true, false);
	Mesh = Component;
}

void FFuryShadows::Show(bool bVisible)
{
	if (Mesh.IsValid()) { Mesh->SetVisibility(bVisible); }
}

void FFuryShadows::Update(const TArray<TObjectPtr<AFuryAthlete>>& Athletes, const FFuryAnimSet& Rig)
{
	if (!Mesh.IsValid() || Athletes.Num() != Fury::NumPlayers) { return; }
	for (int32 i = 0; i < Athletes.Num(); ++i)
	{
		const AFuryAthlete* P = Athletes[i];
		const FVector Chest = P->BoneWorld(Rig.Spine3).GetLocation();
		const FVector Feet[] = { P->BoneWorld(Rig.ToeL).GetLocation(), P->BoneWorld(Rig.ToeR).GetLocation() };
		const FVector MidFeet = (Feet[0] + Feet[1]) * 0.5;
		const FVector2D Lay(Chest.X - MidFeet.X, Chest.Y - MidFeet.Y);
		const float Span = FMath::Min(180.f, static_cast<float>(Lay.Size()));
		const float Clearance = FMath::Max(0.f, static_cast<float>(FMath::Min3(Feet[0].Z, Feet[1].Z, Chest.Z)));
		const float Lift = FMath::Clamp(Clearance / 240.f, 0.f, 1.f);
		const FVector Mid = (Chest + MidFeet) * 0.5;
		const float Facing = P->GetActorRotation().Yaw;
		const float Heading = Span > 35.f ? FMath::RadiansToDegrees(FMath::Atan2(Lay.Y, Lay.X)) : Facing;
		const int32 Base = 3 * i;
		Transforms[Base] = FTransform(FRotator(0.f, Heading, 0.f), FVector(Mid.X, Mid.Y, 1.6f),
			FVector((104.f + Span + 35.f * Lift) / 100.f, 0.9f + 0.35f * Lift, 1.f));
		Opacity[Base] = 0.48f - 0.31f * Lift;
		for (int32 j = 0; j < 2; ++j)
		{
			const FVector& Foot = Feet[j];
			Transforms[Base + j + 1] = FTransform(FRotator(0.f, Facing, 0.f),
				FVector(Foot.X, Foot.Y, 1.8f), FVector(0.53f, 0.36f, 1.f));
			Opacity[Base + j + 1] = 0.5f * FMath::Clamp(1.f - static_cast<float>(Foot.Z) / 58.f, 0.f, 1.f);
		}
	}
	Mesh->BatchUpdateInstancesTransforms(0, Transforms, true, false, true);
	Mesh->SetCustomData(0, Opacity.Num() - 1, Opacity, false);
	Mesh->MarkRenderInstancesDirty();
}
