#pragma once

#include "CoreMinimal.h"

class AActor;
class AFuryAthlete;
class UInstancedStaticMeshComponent;
class FFuryAnimSet;

/** Soft turf contact from the rendered pelvis and cleats, shared by all fourteen athletes. */
struct FFuryShadows
{
	void Init(AActor* Owner);
	void Update(const TArray<TObjectPtr<AFuryAthlete>>& Athletes, const FFuryAnimSet& Rig);
	void Show(bool bVisible);
private:
	TWeakObjectPtr<UInstancedStaticMeshComponent> Mesh;
	TArray<FTransform> Transforms;
	TArray<float> Opacity;
};
