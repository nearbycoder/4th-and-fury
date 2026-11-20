#pragma once

#include "CoreMinimal.h"

class AActor;
class UInstancedStaticMeshComponent;

/**
 * Sparks, dust, flames and fireworks: a small CPU particle system drawn as camera-facing
 * additive quads through one instanced mesh.
 */
class FFuryFX
{
public:
	void Init(AActor* Owner);
	void Tick(float DeltaTime, const FVector& CameraForward, const FVector& CameraRight);

	/** A spray of particles flying out from a point. */
	void Burst(const FVector& Origin, const FLinearColor& Color, int32 Count, float Speed, float Life, float Size, float Brightness = 3.f, float Gravity = 500.f, float UpBias = 0.4f);
	/** One particle with full control. */
	void Emit(const FVector& Origin, const FVector& Velocity, const FLinearColor& Color, float Life, float Size, float Brightness, float Gravity = 0.f, float Drag = 1.5f, float Growth = 0.f);
	/** A firework shell: a bright core and a sphere of falling embers. */
	void Firework(const FVector& Origin, const FLinearColor& Color, float Scale = 1.f);
	/** A lick of flame at a point (Fury mode). */
	void Flame(const FVector& Origin, const FVector& Drift);
	void Clear();
	float ParticleDensity = 1.f;

private:
	struct FParticle
	{
		FVector P, V;
		FLinearColor Color;
		float Life, MaxLife, Size, Growth, Brightness, Gravity, Drag;
	};

	TArray<FParticle> Particles;
	TWeakObjectPtr<UInstancedStaticMeshComponent> Instances;
	TArray<FTransform> Transforms;
	TArray<float> Data;
	int32 PoolSize = 0, LastUsed = 0;
	FRandomStream Random;
};
