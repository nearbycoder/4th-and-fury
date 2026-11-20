#include "FurySim.h"

// What every computer-controlled athlete wants to do each step. Each Think function only says
// where to go and how fast (and occasionally triggers an action); FurySimPlay.cpp moves them.

namespace
{
	using namespace Fury;

	/** Head for a point, easing off when nearly there. */
	void Seek(const FVector2D& From, const FVector2D& To, float TopSpeed, float Arrive, FVector2D& OutWish, float& OutSpeed)
	{
		const FVector2D Delta = To - From;
		const float Dist = Delta.Size();
		if (Dist < 8.f)
		{
			OutWish = FVector2D::ZeroVector;
			OutSpeed = 0.f;
			return;
		}
		OutWish = Delta / Dist;
		OutSpeed = Arrive > 0.f ? TopSpeed * FMath::Clamp(Dist / Arrive, 0.25f, 1.f) : TopSpeed;
	}
}

FVector2D FFurySim::DelayedPos(int32 Index, float Seconds) const
{
	const int32 Back = FMath::Clamp(FMath::RoundToInt32(Seconds * 30.f), 0, TrailLength - 1);
	return Trail[Index][(TrailHead - Back + TrailLength) % TrailLength];
}

FVector2D FFurySim::PursuitPoint(const FFurySimPlayer& Chaser, const FFurySimPlayer& Runner) const
{
	// Run to where he is going, not where he is.
	const float Dist = FVector2D::Distance(Chaser.P, Runner.P);
	const float Time = FMath::Min(Dist / FMath::Max(Chaser.TopSpeed, 1.f), 1.1f);
	return ClampToField(Runner.P + Runner.V * Time * 0.85f, -150.f);
}

void FFurySim::PairBlockers()
{
	// Each lineman takes the rusher lined up nearest to him; nobody is taken twice.
	const int32 Def = Defense();
	bool bTaken[TeamSize] = {};
	for (int32 Slot = 1; Slot <= 3; ++Slot)
	{
		FFurySimPlayer& Blocker = Players[Global(Offense, Slot)];
		Blocker.Mark = INDEX_NONE;
		float Best = TNumericLimits<float>::Max();
		for (int32 Other = 0; Other < TeamSize; ++Other)
		{
			const FFurySimPlayer& Rusher = Players[Global(Def, Other)];
			const bool bRushing = Rusher.Job.Job == EFuryJob::Rush || Rusher.Job.Job == EFuryJob::Blitz;
			if (bTaken[Other] || !bRushing)
			{
				continue;
			}
			const float Dist = FMath::Abs(Rusher.Home.Y - Blocker.Home.Y) + FMath::Abs(Rusher.Home.X - Blocker.Home.X) * 0.5f;
			if (Dist < Best)
			{
				Best = Dist;
				Blocker.Mark = Global(Def, Other);
			}
		}
		if (Blocker.Mark != INDEX_NONE)
		{
			bTaken[Blocker.Mark % TeamSize] = true;
		}
	}
	// Receivers asked to block take the man across from them.
	for (int32 Slot = 4; Slot < TeamSize; ++Slot)
	{
		FFurySimPlayer& Blocker = Players[Global(Offense, Slot)];
		if (Blocker.Job.Job != EFuryJob::RunBlock)
		{
			continue;
		}
		for (int32 Other = 0; Other < TeamSize; ++Other)
		{
			const FFurySimPlayer& Cover = Players[Global(Def, Other)];
			if (Cover.Job.Job == EFuryJob::Man && Cover.Mark == Global(Offense, Slot))
			{
				Blocker.Mark = Global(Def, Other);
			}
		}
	}
}

int32 FFurySim::PickBlockTarget(int32 Blocker, const FVector2D& Protect) const
{
	const FFurySimPlayer& Me = Players[Blocker];
	int32 Best = INDEX_NONE;
	float BestScore = 16.f * Yard;
	for (int32 i = 0; i < NumPlayers; ++i)
	{
		const FFurySimPlayer& O = Players[i];
		if (O.Team == Me.Team || O.bDown || O.Engaged != INDEX_NONE)
		{
			continue;
		}
		// Skip defenders a team-mate is already heading for.
		bool bClaimed = false;
		for (int32 Slot = 0; Slot < TeamSize; ++Slot)
		{
			const int32 Mate = Global(Me.Team, Slot);
			if (Mate != Blocker && Players[Mate].Mark == i && !Players[Mate].bDown && !Players[Mate].bHasBall)
			{
				bClaimed = true;
			}
		}
		if (bClaimed)
		{
			continue;
		}
		const float Score = FVector2D::Distance(Me.P, O.P) * 0.6f + FVector2D::Distance(O.P, Protect);
		if (Score < BestScore)
		{
			BestScore = Score;
			Best = i;
		}
	}
	return Best;
}

/** How open a receiver is, in yards of separation at the catch, plus bonuses for depth. */
float FFurySim::Openness(int32 Receiver, FVector2D& OutCatchPoint, float& OutTime) const
{
	const FFurySimPlayer& R = Players[Receiver];
	const int32 QB = CarrierIndex();
	if (QB == INDEX_NONE || R.bDown || R.Engaged != INDEX_NONE || R.React > 0.25f)
	{
		return -100.f;
	}
	const FFurySimPlayer& Q = Players[QB];
	FVector2D Aim = R.P;
	float T = 0.5f;
	const bool bSettled = R.bRouteDone && R.V.SizeSquared() < 200.f * 200.f;
	for (int32 i = 0; i < 3; ++i)
	{
		T = 0.26f + FVector2D::Distance(Q.P, Aim) / 2700.f;
		Aim = bSettled ? R.P : R.P + R.V * T;
	}
	OutCatchPoint = Aim;
	OutTime = T;
	if (FMath::Abs(Aim.Y) > SidelineY - 60.f || FMath::Abs(Aim.X) > EndLineX - 60.f)
	{
		return -50.f;
	}

	float Nearest = 1.e6f;
	float LanePenalty = 0.f;
	const FVector2D Lane = Aim - Q.P;
	const float LaneLength = FMath::Max(Lane.Size(), 1.f);
	const FVector2D LaneDir = Lane / LaneLength;
	for (int32 i = 0; i < NumPlayers; ++i)
	{
		const FFurySimPlayer& O = Players[i];
		if (O.Team == R.Team || O.bDown)
		{
			continue;
		}
		// Assume a defender keeps doing what he is doing for most of the ball's flight.
		const FVector2D Future = O.P + O.V * FMath::Min(T, 0.85f);
		Nearest = FMath::Min(Nearest, FMath::Min(FVector2D::Distance(Future, Aim), FVector2D::Distance(O.P, R.P) + 60.f));
		// A defender sitting in the throwing lane can knock it down or pick it off.
		const float Along = FVector2D::DotProduct(O.P - Q.P, LaneDir);
		if (Along > 1.5f * Yard && Along < LaneLength * 0.8f)
		{
			const float Off = FMath::Abs(FVector2D::CrossProduct(O.P - Q.P, LaneDir));
			if (Off < 115.f)
			{
				LanePenalty = 3.f;
			}
		}
	}
	// Separation is what matters; depth, the designed first read and the end zone only break ties.
	const float Depth = (Aim.X - LosX) * OffenseDir() / Yard;
	float Score = FMath::Min(Nearest / Yard, 8.f) + FMath::Clamp(Depth, -3.f, 25.f) * 0.05f - LanePenalty;
	if (R.Slot == CurrentOff.Primary) { Score += 0.6f; }
	if (Aim.X * OffenseDir() > GoalX) { Score += 1.f; }
	return Score;
}

// ---------------------------------------------------------------------------------------------
// Dispatch
// ---------------------------------------------------------------------------------------------

void FFurySim::ThinkPlayer(FFurySimPlayer& P, int32 Index, float Dt, FVector2D& OutWish, float& OutSpeed)
{
	OutWish = FVector2D::ZeroVector;
	OutSpeed = MaxSpeed(P, false);
	if (P.React > 0.f)
	{
		P.React -= Dt;
		return;
	}

	// Loose ball: the two nearest on each side go for it, everyone else gets between it and their goal.
	if (Ball.State == EFuryBallState::Loose)
	{
		const FVector2D Spot = FVector2D(Ball.Pos.X, Ball.Pos.Y) + FVector2D(Ball.Vel.X, Ball.Vel.Y) * 0.25f;
		int32 Closer = 0;
		const float MyDist = FVector2D::DistSquared(P.P, Spot);
		for (int32 Slot = 0; Slot < TeamSize; ++Slot)
		{
			const FFurySimPlayer& Mate = Players[Global(P.Team, Slot)];
			if (&Mate != &P && !Mate.bDown && FVector2D::DistSquared(Mate.P, Spot) < MyDist)
			{
				++Closer;
			}
		}
		if (Closer < 2)
		{
			Seek(P.P, Spot, OutSpeed, 0.f, OutWish, OutSpeed);
			if (MyDist < FMath::Square(2.3f * Yard) && MyDist > FMath::Square(1.2f * Yard) && Ball.Pos.Z < 60.f && P.Cooldown <= 0.f && Chance(Dt * 2.5f))
			{
				SetAct(P, EFuryAct::Dive, 0, 0.55f, 0.f, true);
				P.Launch = (Spot - P.P).GetSafeNormal() * 1150.f;
				P.Yaw = AngleOf(P.Launch);
				P.Cooldown = 1.2f;
			}
		}
		else
		{
			Seek(P.P, Spot - FVector2D(Dir(P.Team) * 4.f * Yard, 0.f), OutSpeed * 0.8f, 200.f, OutWish, OutSpeed);
		}
		return;
	}

	if (P.bHasBall)
	{
		const bool bPasser = P.Team == Offense && P.Slot == 0 && !bChangeOfPossession && !bPassThrown && !bBallCrossedLine
			&& (PlayType == EFuryPlayType::Scrimmage || PlayType == EFuryPlayType::TwoPoint);
		if (bPasser)
		{
			ThinkPasser(P, Index, Dt, OutWish, OutSpeed);
		}
		else
		{
			ThinkCarrier(P, Index, Dt, OutWish, OutSpeed);
		}
		return;
	}

	const bool bKickInAir = Ball.State == EFuryBallState::Kick;
	const int32 Carrier = CarrierIndex();
	bool bAttacking = BallTeam == P.Team;
	if (bKickInAir && Ball.Thrower != INDEX_NONE)
	{
		bAttacking = P.Team != Players[Ball.Thrower].Team;      // the receiving side is "on offense" for a kick in the air
	}
	if (Ball.State == EFuryBallState::Tee && PlayType == EFuryPlayType::Kickoff)
	{
		return;                                                   // waiting for the kick
	}

	if (!bAttacking)
	{
		ThinkDefender(P, Index, Dt, OutWish, OutSpeed);
	}
	else if (P.Job.Job == EFuryJob::Route && !bBallCrossedLine && Carrier != INDEX_NONE && Players[Carrier].Slot == 0)
	{
		ThinkReceiver(P, Index, Dt, OutWish, OutSpeed);
	}
	else if (Ball.State == EFuryBallState::Pass && (Ball.Target == Index || P.Job.Job == EFuryJob::Route))
	{
		ThinkReceiver(P, Index, Dt, OutWish, OutSpeed);
	}
	else
	{
		ThinkBlocker(P, Index, Dt, OutWish, OutSpeed);
	}
}

// ---------------------------------------------------------------------------------------------
// Offense
// ---------------------------------------------------------------------------------------------

void FFurySim::ThinkReceiver(FFurySimPlayer& P, int32 Index, float Dt, FVector2D& OutWish, float& OutSpeed)
{
	// The ball is in the air for me: get under it.
	if (Ball.State == EFuryBallState::Pass && Ball.Target == Index)
	{
		const FVector2D Spot = Ball.Land();
		const float Left = Ball.Duration - Ball.Time;
		const float Dist = FVector2D::Distance(P.P, Spot);
		if (Left > 0.05f)
		{
			// Arrive with the ball rather than early, so the catch is made in stride.
			Seek(P.P, Spot, OutSpeed, 0.f, OutWish, OutSpeed);
			OutSpeed = FMath::Min(OutSpeed, FMath::Max(Dist / Left, 200.f));
			if (Left < 0.35f && Ball.To.Z > 150.f)
			{
				P.JumpLeft = 0.3f;
			}
		}
		else
		{
			Seek(P.P, FVector2D(Ball.Pos.X, Ball.Pos.Y), OutSpeed, 0.f, OutWish, OutSpeed);
		}
		return;
	}

	if (!P.bRouteDone)
	{
		if (P.PathIndex >= P.Path.Num())
		{
			P.bRouteDone = true;
		}
		else
		{
			const FVector2D Target = P.Path[P.PathIndex];
			if (FVector2D::DistSquared(P.P, Target) < 75.f * 75.f)
			{
				++P.PathIndex;
			}
			Seek(P.P, Target, OutSpeed * 0.97f, 0.f, OutWish, OutSpeed);
			return;
		}
	}

	// Route finished. A route that ends coming back to the ball settles; anything else keeps running.
	const int32 Count = P.Path.Num();
	const float D = OffenseDir();
	const bool bSettle = Count >= 2 && (P.Path[Count - 1].X - P.Path[Count - 2].X) * D < 0.f;
	if (bSettle || Count == 0)
	{
		const int32 QB = Global(Offense, 0);
		P.bFace = true;
		P.FaceYaw = AngleOf(Players[QB].P - P.P);
		// Drift away from the nearest defender to stay open.
		const int32 Near = NearestOpponent(Index, 3.f * Yard);
		if (Near != INDEX_NONE)
		{
			OutWish = (P.P - Players[Near].P).GetSafeNormal();
			OutWish.X *= 0.3f;
			OutSpeed *= 0.45f;
		}
		return;
	}
	FVector2D Heading = Count >= 2 ? (P.Path[Count - 1] - P.Path[Count - 2]).GetSafeNormal() : FVector2D(D, 0.f);
	// Bend back into the field instead of running out of it.
	if (FMath::Abs(P.P.Y) > SidelineY - 4.f * Yard && P.P.Y * Heading.Y > 0.f)
	{
		Heading.Y = -Heading.Y * 0.4f;
		Heading.X = D;
	}
	if (P.P.X * D > EndLineX - 3.f * Yard)
	{
		Heading.X = 0.f;
		Heading.Y = P.P.Y > 0.f ? -1.f : 1.f;
	}
	OutWish = Heading.GetSafeNormal();
	OutSpeed *= 0.85f;
}

void FFurySim::ThinkBlocker(FFurySimPlayer& P, int32 Index, float Dt, FVector2D& OutWish, float& OutSpeed)
{
	const int32 Carrier = CarrierIndex();
	const float D = Dir(P.Team);
	const bool bKickPlay = PlayType == EFuryPlayType::Kickoff || PlayType == EFuryPlayType::Punt;

	// Kick return: drop back in front of where the ball will come down, then lead the returner.
	if (bKickPlay && Ball.State == EFuryBallState::Kick && P.Job.Job == EFuryJob::ReturnBlock)
	{
		const FVector2D Wedge = Ball.Land() + FVector2D(D * 11.f * Yard, (P.Slot - 2.5f) * 3.2f * Yard);
		Seek(P.P, ClampToField(Wedge, 150.f), OutSpeed, 250.f, OutWish, OutSpeed);
		return;
	}
	// Punt coverage men and the kicking team after a kick simply chase the ball.
	if (bKickPlay && Ball.State == EFuryBallState::Kick)
	{
		ThinkDefender(P, Index, Dt, OutWish, OutSpeed);
		return;
	}

	const bool bCarrierIsMate = Carrier != INDEX_NONE && Players[Carrier].Team == P.Team;
	const bool bPocket = bCarrierIsMate && Players[Carrier].Slot == 0 && !bBallCrossedLine && !bChangeOfPossession && CurrentOff.Kind != EFuryPlayKind::Run
		&& (PlayType == EFuryPlayType::Scrimmage || PlayType == EFuryPlayType::TwoPoint || PlayType == EFuryPlayType::Punt || PlayType == EFuryPlayType::FieldGoal || PlayType == EFuryPlayType::ExtraPoint);
	const bool bScreenRelease = CurrentOff.bScreen && LiveTime > 0.95f && P.Pos == EFuryPos::OL;

	FVector2D Protect = bCarrierIsMate ? Players[Carrier].P : FVector2D(Ball.Pos.X, Ball.Pos.Y);
	if (Ball.State == EFuryBallState::Pass)
	{
		Protect = Ball.Land();
	}

	// Is the man I was blocking still worth blocking?
	if (P.Mark != INDEX_NONE)
	{
		const FFurySimPlayer& M = Players[P.Mark];
		if (M.bDown || (M.Engaged != INDEX_NONE && M.Engaged != Index) || M.Team == P.Team)
		{
			P.Mark = INDEX_NONE;
		}
	}

	if (bPocket && !bScreenRelease)
	{
		// Pass protection: stay between my rusher and the quarterback.
		if (P.Mark == INDEX_NONE)
		{
			P.Think -= Dt;
			if (P.Think <= 0.f)
			{
				P.Think = 0.25f;
				const int32 Threat = PickBlockTarget(Index, Protect);
				if (Threat != INDEX_NONE && FVector2D::Distance(Players[Threat].P, Protect) < 9.f * Yard)
				{
					P.Mark = Threat;
				}
			}
		}
		if (P.Mark == INDEX_NONE)
		{
			const FVector2D Spot = P.Home - FVector2D(D * 1.4f * Yard, 0.f);
			Seek(P.P, Spot, OutSpeed * 0.6f, 150.f, OutWish, OutSpeed);
			P.bFace = true;
			P.FaceYaw = D > 0.f ? 0.f : UE_PI;
			return;
		}
		const FFurySimPlayer& M = Players[P.Mark];
		const FVector2D Between = M.P + (Protect - M.P).GetSafeNormal() * (M.Radius + P.Radius + 6.f);
		Seek(P.P, Between, OutSpeed, 0.f, OutWish, OutSpeed);
		P.bFace = true;
		P.FaceYaw = AngleOf(M.P - P.P);
		if (FVector2D::DistSquared(P.P, M.P) < FMath::Square(P.Radius + M.Radius + 20.f))
		{
			// How long the block holds: muscle against muscle, with some luck.
			const bool bLineman = P.Pos == EFuryPos::OL;
			float Hold = (bLineman ? RandRange(2.3f, 3.7f) : RandRange(0.9f, 1.7f)) - (M.Power - P.Power) * 1.4f;
			if (M.Seat == INDEX_NONE) { Hold -= CpuSkill * 0.5f; }
			Engage(Index, P.Mark, FMath::Max(Hold, 0.6f));
		}
		return;
	}

	// Run blocking and blocking downfield: find someone to hit near the ball, or escort the runner.
	if (P.Mark == INDEX_NONE)
	{
		P.Think -= Dt;
		if (P.Think <= 0.f)
		{
			P.Think = 0.2f;
			P.Mark = PickBlockTarget(Index, Protect);
		}
	}
	if (P.Mark != INDEX_NONE)
	{
		const FFurySimPlayer& M = Players[P.Mark];
		Seek(P.P, M.P + M.V * 0.15f, OutSpeed, 0.f, OutWish, OutSpeed);
		if (FVector2D::DistSquared(P.P, M.P) < FMath::Square(P.Radius + M.Radius + 20.f))
		{
			// Blocks in the open field (and on kick returns especially) do not last long.
			const float Hold = (bKickPlay ? RandRange(0.5f, 1.1f) : RandRange(1.1f, 2.2f)) - (M.Power - P.Power) * 1.2f;
			Engage(Index, P.Mark, FMath::Max(Hold, 0.4f));
		}
		return;
	}
	if (bCarrierIsMate)
	{
		const FVector2D Escort = Players[Carrier].P + FVector2D(D * 4.5f * Yard, (P.Slot - 3) * 1.6f * Yard);
		Seek(P.P, ClampToField(Escort, 100.f), OutSpeed, 200.f, OutWish, OutSpeed);
	}
	else
	{
		Seek(P.P, Protect, OutSpeed * 0.8f, 300.f, OutWish, OutSpeed);
	}
}

void FFurySim::ThinkPasser(FFurySimPlayer& P, int32 Index, float Dt, FVector2D& OutWish, float& OutSpeed)
{
	const float D = OffenseDir();

	// Designed runs: get the ball to the back at the mesh point.
	if (CurrentOff.Kind == EFuryPlayKind::Run && P.Job.Job != EFuryJob::Keeper)
	{
		int32 Back = INDEX_NONE;
		for (int32 Slot = 0; Slot < TeamSize; ++Slot)
		{
			if (Players[Global(Offense, Slot)].Job.Job == EFuryJob::Carry)
			{
				Back = Global(Offense, Slot);
			}
		}
		if (Back != INDEX_NONE && !Players[Back].bDown && LiveTime < 2.f)
		{
			FFurySimPlayer& B = Players[Back];
			P.bFace = true;
			P.FaceYaw = AngleOf(B.P - P.P);
			const FVector2D Mesh = B.Path.Num() > 0 ? B.Path[0] : P.P;
			const float Gap = FVector2D::Distance(P.P, B.P);
			if (FVector2D::DistSquared(B.P, Mesh) < 120.f * 120.f || Gap < 130.f)
			{
				P.bHasBall = false;
				if (Gap < 200.f)
				{
					SetAct(P, EFuryAct::Handoff, 0, 0.45f, 0.2f, false);
					Ball.Thrower = Index;
					GiveBall(Back);
					Emit(EFuryEvent::Handoff, Offense, Index, Back);
				}
				else
				{
					// A toss: a short flight that the back cannot miss.
					SetAct(P, EFuryAct::Throw, 0, 0.3f, 0.f, false);
					Ball.State = EFuryBallState::Snap;
					Ball.Holder = INDEX_NONE;
					Ball.Thrower = Index;
					Ball.Target = Back;
					Ball.From = FVector(P.P.X, P.P.Y, 120.f);
					Ball.To = FVector(B.P.X, B.P.Y, 110.f);
					Ball.Time = 0.f;
					Ball.Duration = 0.26f;
					Emit(EFuryEvent::Pitch, Offense, Index, Back);
				}
				bBallCrossedLine = true;
			}
			return;
		}
		ThinkCarrier(P, Index, Dt, OutWish, OutSpeed);       // the back never showed: keep it
		return;
	}
	if (P.Job.Job == EFuryJob::Keeper)
	{
		ThinkCarrier(P, Index, Dt, OutWish, OutSpeed);
		return;
	}

	// Drop back (or roll out), facing downfield.
	P.bFace = true;
	P.FaceYaw = D > 0.f ? 0.f : UE_PI;
	FVector2D Spot = P.Home - FVector2D(D * CurrentOff.Drop * Yard, 0.f);
	if (P.Path.Num() > 0)
	{
		if (P.PathIndex < P.Path.Num() && FVector2D::DistSquared(P.P, P.Path[P.PathIndex]) < 80.f * 80.f)
		{
			++P.PathIndex;
		}
		Spot = P.Path[FMath::Min(P.PathIndex, P.Path.Num() - 1)];
	}
	const int32 Rusher = NearestOpponent(Index, 6.f * Yard);
	const float Pressure = Rusher != INDEX_NONE ? FVector2D::Distance(P.P, Players[Rusher].P) : 1.e6f;

	if (!P.bScramble)
	{
		Seek(P.P, Spot, OutSpeed * 0.82f, 120.f, OutWish, OutSpeed);
		// Slide away from a rusher who has broken through.
		if (Pressure < 3.f * Yard)
		{
			const FVector2D Away = (P.P - Players[Rusher].P).GetSafeNormal();
			OutWish = (OutWish * 0.3f + FVector2D(Away.X * 0.4f, Away.Y)).GetSafeNormal();
			OutSpeed = P.TopSpeed * 0.9f;
		}
	}

	// Read the field a few times a second.
	const float FirstLook = CurrentOff.bPlayAction ? 1.05f : CurrentOff.Drop <= 1.6f ? 0.5f : 0.85f;
	P.Think -= Dt;
	if (LiveTime >= FirstLook && P.Think <= 0.f)
	{
		P.Think = 0.16f;
		int32 Best = INDEX_NONE;
		float BestScore = -1.e6f;
		for (int32 Slot = 4; Slot < TeamSize; ++Slot)
		{
			const int32 Target = Global(Offense, Slot);
			if (Players[Target].Job.Job != EFuryJob::Route)
			{
				continue;
			}
			FVector2D Point;
			float Time;
			// Weaker computer quarterbacks misjudge how open people are.
			const float Score = Openness(Target, Point, Time) + RandRange(-1.f, 1.f) * (1.f - CpuSkill) * 2.2f;
			if (Score > BestScore)
			{
				BestScore = Score;
				Best = Target;
			}
		}
		// Wants about three yards of daylight at first; settles for less as the clock and the rush close in.
		float Need = 3.6f - 0.8f * FMath::Max(0.f, LiveTime - 1.6f);
		if (Pressure < 3.f * Yard) { Need -= 1.2f; }
		if (CurrentOff.bScreen && LiveTime > 1.f) { Need -= 1.5f; }
		Need = FMath::Max(Need, 1.3f);
		if (Best != INDEX_NONE && BestScore >= Need)
		{
			StartThrow(Index, Best);
			return;
		}
		// Nobody open and the pocket is gone: throw it up anyway, or run for it.
		if (Pressure < 1.9f * Yard || LiveTime > 3.8f)
		{
			if (Best != INDEX_NONE && BestScore > 0.8f && Chance(0.45f))
			{
				StartThrow(Index, Best);
				return;
			}
			P.bScramble = true;
		}
	}

	if (P.bScramble)
	{
		ThinkCarrier(P, Index, Dt, OutWish, OutSpeed);
		P.bFace = false;
	}
}

void FFurySim::ThinkCarrier(FFurySimPlayer& P, int32 Index, float Dt, FVector2D& OutWish, float& OutSpeed)
{
	const float D = Dir(P.Team);
	const float LineDir = OffenseDir();

	// Bodies in the way - his own blockers, and defenders locked up with them - cannot be run
	// through. With one dead ahead the runner slides along the pile toward the nearer edge of it,
	// instead of jogging on the spot against somebody's back.
	auto SlidePastBodies = [this, &P, Index](FVector2D& Wish)
	{
		const FVector2D Forward = Wish.GetSafeNormal();
		if (Forward.IsNearlyZero())
		{
			return;
		}
		const FVector2D Side(-Forward.Y, Forward.X);
		float Sum = 0.f;
		int32 Count = 0;
		for (int32 i = 0; i < NumPlayers; ++i)
		{
			const FFurySimPlayer& O = Players[i];
			if (i == Index || O.bDown || (O.Team != P.Team && O.Engaged == INDEX_NONE))
			{
				continue;      // free defenders are tacklers, and are dealt with as threats
			}
			const FVector2D Rel = O.P - P.P;
			const float Ahead = FVector2D::DotProduct(Rel, Forward);
			const float Across = FVector2D::DotProduct(Rel, Side);
			if (Ahead > -15.f && Ahead < 175.f && FMath::Abs(Across) < P.Radius + O.Radius + 22.f)
			{
				Sum += Across;
				++Count;
			}
		}
		if (Count == 0)
		{
			return;
		}
		const float Mean = Sum / Count;
		// Round the side he is already nearer to; dead centre, toward the wide side of the field.
		float Go = FMath::Abs(Mean) > 6.f ? -FMath::Sign(Mean) : FMath::Sign(FVector2D::DotProduct(Side, FVector2D(0.f, -P.P.Y)));
		if (Go == 0.f) { Go = 1.f; }
		Wish = (Forward * 0.3f + Side * Go).GetSafeNormal();
	};

	// A designed run follows its path until it is through the line - while the design holds up.
	// After a couple of seconds behind the line it has not: improvise.
	const bool bDesigned = (P.Job.Job == EFuryJob::Carry || P.Job.Job == EFuryJob::Keeper) && P.Team == Offense && !bChangeOfPossession && LiveTime < 2.8f;
	if (bDesigned && P.PathIndex < P.Path.Num() && (P.P.X - LosX) * LineDir < 3.f * Yard)
	{
		const FVector2D Target = P.Path[P.PathIndex];
		if (FVector2D::DistSquared(P.P, Target) < 90.f * 90.f)
		{
			++P.PathIndex;
		}
		Seek(P.P, Target, OutSpeed, 0.f, OutWish, OutSpeed);
		SlidePastBodies(OutWish);
		return;
	}

	// Open field: head for the end zone, bending away from tacklers and the sideline.
	if (P.Burst <= 0.f && P.BurstCool <= 0.f && NearestOpponent(Index, 9.f * Yard) != INDEX_NONE)
	{
		P.Burst = 1.2f + CpuSkill;
		P.BurstCool = P.Burst + 3.f - CpuSkill;
	}
	FVector2D Steer(D, 0.f);
	int32 Threat = INDEX_NONE;
	float ThreatDist = 2.6f * Yard;
	for (int32 i = 0; i < NumPlayers; ++i)
	{
		const FFurySimPlayer& O = Players[i];
		if (O.Team == P.Team || O.bDown || O.Engaged != INDEX_NONE)
		{
			continue;
		}
		const FVector2D Rel = O.P + O.V * 0.2f - P.P;
		const float Ahead = Rel.X * D;
		const float Dist = Rel.Size();
		if (Ahead < -1.5f * Yard || Dist > 9.f * Yard)
		{
			continue;
		}
		const float Weight = FMath::Square(1.f - Dist / (9.f * Yard));
		Steer.Y += (Rel.Y > 0.f ? -1.f : 1.f) * Weight * (Ahead > 0.f ? 2.4f : 0.9f);
		if (Dist < ThreatDist && Ahead > -40.f)
		{
			ThreatDist = Dist;
			Threat = i;
		}
	}
	const float Edge = FMath::Abs(P.P.Y) - (SidelineY - 3.5f * Yard);
	if (Edge > 0.f)
	{
		Steer.Y -= FMath::Sign(P.P.Y) * (1.f + Edge / Yard);
	}
	Steer.X = D * FMath::Max(FMath::Abs(Steer.X), 0.35f);
	OutWish = Steer.GetSafeNormal();

	// A quarterback scrambling behind the line just tries to get outside the rush first.
	if (P.Slot == 0 && P.Team == Offense && (P.P.X - LosX) * LineDir < -1.f * Yard && !bChangeOfPossession && Threat != INDEX_NONE)
	{
		OutWish = FVector2D(D * 0.45f, P.P.Y >= Players[Threat].P.Y ? 1.f : -1.f).GetSafeNormal();
	}
	SlidePastBodies(OutWish);

	// Moves. Better computer teams use them more.
	if (Threat != INDEX_NONE && P.Cooldown <= 0.f)
	{
		P.Think -= Dt;
		if (P.Think <= 0.f)
		{
			P.Think = 0.12f;
			const FFurySimPlayer& T = Players[Threat];
			const float Roll = Rand();
			const bool bReturn = PlayType == EFuryPlayType::Kickoff || PlayType == EFuryPlayType::Punt;
			const float Use = (0.25f + 0.45f * CpuSkill) * (bReturn ? 0.5f : 1.f);
			if (T.Act == EFuryAct::Dive && Roll < Use)
			{
				SetAct(P, EFuryAct::Hurdle, 0, 0.6f, 0.f, true);
				P.EvadeLeft = 0.5f;
				P.Launch = OutWish * OutSpeed * 0.95f;
				P.Cooldown = 1.6f;
				Emit(EFuryEvent::Hurdle, P.Team, Index);
			}
			else if (Roll < Use * 0.4f)
			{
				SetAct(P, EFuryAct::Spin, 0, 0.5f, 0.f, false);
				P.EvadeLeft = 0.42f;
				P.Cooldown = 1.6f;
				Emit(EFuryEvent::Spin, P.Team, Index);
			}
			else if (Roll < Use * 0.75f)
			{
				SetAct(P, EFuryAct::StiffArm, 0, 0.45f, 0.15f, false);
				P.StiffLeft = 0.45f;
				P.Cooldown = 1.5f;
			}
			else if (Roll < Use)
			{
				// Juke: a hard sidestep away from the tackler.
				const bool bLeft = (T.P.Y - P.P.Y) * D > 0.f;
				SetAct(P, EFuryAct::Juke, bLeft ? 0 : 1, 0.35f, 0.f, false);
				P.V = FVector2D(P.V.X * 0.8f, (T.P.Y > P.P.Y ? -1.f : 1.f) * P.TopSpeed * 0.8f);
				P.EvadeLeft = 0.2f;
				P.Cooldown = 1.4f;
				Emit(EFuryEvent::Juke, P.Team, Index);
			}
			else
			{
				P.Cooldown = 0.5f;
			}
		}
	}
	if (P.Act == EFuryAct::Spin)
	{
		OutSpeed *= 0.85f;
	}
}

// ---------------------------------------------------------------------------------------------
// Defense
// ---------------------------------------------------------------------------------------------

void FFurySim::ThinkDefender(FFurySimPlayer& P, int32 Index, float Dt, FVector2D& OutWish, float& OutSpeed)
{
	const float D = OffenseDir();
	const int32 Carrier = CarrierIndex();
	const FFurySimPlayer& QB = Players[Global(Offense, 0)];

	// A kick in the air: cover it in lanes, converging as it comes down.
	if (Ball.State == EFuryBallState::Kick)
	{
		const FVector2D Land = Ball.Land();
		const float Lane = P.Home.Y;
		const float Blend = FMath::Clamp(Ball.Time / FMath::Max(Ball.Duration, 0.1f), 0.f, 1.f);
		const FVector2D Target(Land.X - Dir(P.Team) * 1.5f * Yard, FMath::Lerp(Lane, Land.Y, 0.35f + 0.6f * Blend));
		Seek(P.P, Target, P.Job.Job == EFuryJob::Kicker || P.Job.Job == EFuryJob::Punter ? OutSpeed * 0.5f : OutSpeed, 0.f, OutWish, OutSpeed);
		return;
	}

	// The ball is thrown: break on it after a beat.
	if (Ball.State == EFuryBallState::Pass)
	{
		if (!P.bBroke)
		{
			P.Think -= Dt;
			if (P.Think <= 0.f)
			{
				P.bBroke = true;
			}
		}
		const FVector2D Land = Ball.Land();
		const bool bMyMan = P.Mark != INDEX_NONE && P.Mark == Ball.Target;
		const bool bNear = FVector2D::DistSquared(P.P, Land) < FMath::Square(13.f * Yard);
		if (P.bBroke && (bMyMan || bNear))
		{
			// Aim for the catch point, slightly on the receiver's upfield shoulder.
			Seek(P.P, Land + FVector2D(D * 40.f, 0.f), OutSpeed, 0.f, OutWish, OutSpeed);
			const float Left = Ball.Duration - Ball.Time;
			if (Left < 0.3f && FVector2D::DistSquared(P.P, Land) < FMath::Square(2.2f * Yard))
			{
				P.JumpLeft = 0.3f;
			}
			return;
		}
		if (P.bBroke)
		{
			Seek(P.P, Land, OutSpeed * 0.9f, 0.f, OutWish, OutSpeed);
			return;
		}
		// Not reacting yet: carry on with the assignment below.
	}

	// Rushers always go for whoever has the ball. Everyone else stays on assignment until they
	// read that the ball is out of the pocket (a hand-off, a scramble past the line, a catch) -
	// and that read takes a moment, so a defense never simply knows a run is coming.
	// A quarterback keeping it on a designed run stops being a passer once he tucks it, and nobody
	// gets to stand in the pocket all night: after a while the coverage comes down too.
	const bool bPocketOver = Carrier != INDEX_NONE && (LiveTime > 8.f || (Players[Carrier].Job.Job == EFuryJob::Keeper && LiveTime > 3.f));
	const bool bPasserInPocket = Carrier != INDEX_NONE && Players[Carrier].Team == Offense && Players[Carrier].Slot == 0
		&& !bBallCrossedLine && !bChangeOfPossession && !bPocketOver;
	const bool bRushJob = P.Job.Job == EFuryJob::Rush || P.Job.Job == EFuryJob::Blitz;
	const bool bEnemyCarrier = Carrier != INDEX_NONE && Players[Carrier].Team != P.Team;
	if (bEnemyCarrier && !bPasserInPocket && !P.bPursue)
	{
		if (P.ReadLeft < 0.f)
		{
			const bool bKick = PlayType == EFuryPlayType::Kickoff || PlayType == EFuryPlayType::Punt;
			P.ReadLeft = (bRushJob || bKick || bPassThrown) ? 0.f : RandRange(0.2f, 0.42f) * (1.35f - 0.7f * CpuSkill);
		}
		P.ReadLeft -= Dt;
		P.bPursue = P.ReadLeft <= 0.f;
	}
	// A spy goes as soon as the quarterback heads for the line or breaks the pocket.
	if (bPasserInPocket && P.Job.Job == EFuryJob::Spy)
	{
		const FFurySimPlayer& Q = Players[Carrier];
		if ((Q.P.X - LosX) * D > -1.8f * Yard || FMath::Abs(Q.P.Y - BallY) > 7.f * Yard)
		{
			P.bPursue = true;
		}
	}
	if (bEnemyCarrier && (bPasserInPocket ? (bRushJob || P.bPursue) : P.bPursue))
	{
		const FFurySimPlayer& C = Players[Carrier];
		// Computer defenders have a turbo of their own: a spurt when the runner is in range, then a breather.
		if (!bPasserInPocket && P.Burst <= 0.f && P.BurstCool <= 0.f && FVector2D::DistSquared(P.P, C.P) < FMath::Square(16.f * Yard))
		{
			P.Burst = 1.5f + CpuSkill;
			P.BurstCool = P.Burst + 2.6f - CpuSkill * 1.2f;
		}
		const FVector2D Target = bPasserInPocket ? C.P : PursuitPoint(P, C);
		Seek(P.P, Target, MaxSpeed(P, false), 0.f, OutWish, OutSpeed);
		// A runner on turbo does not simply run away from everybody: the chase matches most of it.
		if (C.Seat != INDEX_NONE && C.V.SizeSquared() > FMath::Square(C.TopSpeed * 1.05f))
		{
			OutSpeed = FMath::Max(OutSpeed, P.TopSpeed * (1.f + 0.16f * (0.5f + 0.7f * CpuSkill)));
		}

		// Leave the feet when he is about to get away.
		const float Dist = FVector2D::Distance(P.P, C.P);
		if (Dist < 3.3f * Yard && Dist > 1.3f * Yard && P.Cooldown <= 0.f)
		{
			const float Closing = FVector2D::DotProduct(P.V - C.V, (C.P - P.P).GetSafeNormal());
			if (Closing < 160.f && Chance(Dt * (1.2f + 2.5f * CpuSkill)))
			{
				SetAct(P, EFuryAct::Dive, 0, 0.55f, 0.f, true);
				P.Launch = (C.P + C.V * 0.18f - P.P).GetSafeNormal() * 1250.f;
				P.Yaw = AngleOf(P.Launch);
				P.Cooldown = 1.2f;
				Emit(EFuryEvent::Dive, P.Team, Index);
			}
		}
		return;
	}

	switch (P.Job.Job)
	{
	case EFuryJob::Man:
	{
		if (P.Mark == INDEX_NONE)
		{
			break;
		}
		const FFurySimPlayer& R = Players[P.Mark];
		// React a moment late, and give ground early in the route.
		const float Lag = FMath::Clamp(0.3f - CpuSkill * 0.22f - (TeamInfo(P.Team).Defense - 3) * 0.02f, 0.06f, 0.32f);
		const FVector2D Seen = DelayedPos(P.Mark, Lag);
		const float Cushion = FMath::Max(1.f, P.Job.Cushion - LiveTime * 3.5f);
		const FVector2D Target = Seen + R.V * 0.12f + FVector2D(D * Cushion * Yard, R.P.Y > 0.f ? -35.f : 35.f);
		Seek(P.P, Target, OutSpeed, 60.f, OutWish, OutSpeed);
		if (FVector2D::DistSquared(P.P, Target) < 150.f * 150.f)
		{
			P.bFace = true;
			P.FaceYaw = AngleOf(QB.P - P.P);
		}
		return;
	}
	case EFuryJob::Zone:
	{
		// Sit in the zone; pick up the nearest receiver who wanders into it, staying on top of him.
		const FVector2D Centre = ClampToField(ToWorld(P.Job.Zone), 100.f);
		FVector2D Target = Centre;
		float Best = P.Job.Radius * Yard;
		for (int32 Slot = 4; Slot < TeamSize; ++Slot)
		{
			const FFurySimPlayer& R = Players[Global(Offense, Slot)];
			const float Dist = FVector2D::Distance(R.P, Centre);
			if (Dist < Best && !R.bDown)
			{
				Best = Dist;
				Target = DelayedPos(Global(Offense, Slot), 0.15f) + FVector2D(D * 1.6f * Yard, 0.f);
			}
		}
		Seek(P.P, Target, OutSpeed * 0.95f, 120.f, OutWish, OutSpeed);
		P.bFace = true;
		P.FaceYaw = AngleOf(QB.P - P.P);
		return;
	}
	case EFuryJob::Spy:
	{
		const FVector2D Target(LosX + D * 4.f * Yard, QB.P.Y);
		Seek(P.P, Target, OutSpeed * 0.9f, 120.f, OutWish, OutSpeed);
		P.bFace = true;
		P.FaceYaw = AngleOf(QB.P - P.P);
		return;
	}
	case EFuryJob::ReturnBlock:
	case EFuryJob::Returner:
		// Waiting for the kick.
		P.bFace = true;
		P.FaceYaw = AngleOf(FVector2D(Ball.Pos.X, Ball.Pos.Y) - P.P);
		return;
	default:
		break;
	}

	// Rushers with nobody in particular to hit, and anything unexpected: go to the ball.
	Seek(P.P, FVector2D(Ball.Pos.X, Ball.Pos.Y), OutSpeed, 0.f, OutWish, OutSpeed);
}

// ---------------------------------------------------------------------------------------------
// Between plays
// ---------------------------------------------------------------------------------------------

void FFurySim::ThinkAfterWhistle(FFurySimPlayer& P, int32 Index, float Dt, FVector2D& OutWish, float& OutSpeed)
{
	OutWish = FVector2D::ZeroVector;
	OutSpeed = P.TopSpeed * 0.45f;

	if ((Phase == EFuryPhase::Celebrate && PhaseTime <= 1.6f) || Phase == EFuryPhase::GameOver)
	{
		const int32 Happy = Phase == EFuryPhase::GameOver ? Winner() : ScoringTeam;
		if (P.Team != Happy)
		{
			if (P.Act != EFuryAct::Dejected && PhaseTime > 0.6f)
			{
				SetAct(P, EFuryAct::Dejected, 0, 0.f, 0.f, true);
			}
			return;
		}
		if (Index == Scorer && Phase == EFuryPhase::Celebrate)
		{
			if (P.Act != EFuryAct::Celebrate && PhaseTime > 0.25f)
			{
				const int32 Style = Random.RandRange(1, 2);
				SetAct(P, EFuryAct::Celebrate, static_cast<uint8>(Style), 0.f, 0.f, true);
			}
			return;
		}
		// Team-mates run to the scorer (or just whoop it up after the final whistle).
		const FVector2D Party = Scorer != INDEX_NONE && Phase == EFuryPhase::Celebrate ? Players[Scorer].P : P.P;
		const FVector2D Spot = Party + FromAngle(P.Slot * 0.9f) * 230.f;
		if (FVector2D::DistSquared(P.P, Spot) > 120.f * 120.f && Phase == EFuryPhase::Celebrate)
		{
			Seek(P.P, Spot, P.TopSpeed * 0.8f, 150.f, OutWish, OutSpeed);
		}
		else if (P.Act != EFuryAct::Celebrate)
		{
			SetAct(P, EFuryAct::Celebrate, static_cast<uint8>(1 + (P.Slot & 1)), 0.f, 0.f, true);
			P.Yaw = AngleOf(Party - P.P);
		}
		return;
	}

	if (AfterWhistle())
	{
		// A couple of CPU players on each side join in. They take a breather
		// between attempts so a human can get back up and answer.
		if ((P.Slot + PlayCount) % 3 != 0) { return; }
		P.Think -= Dt;
		if (P.Cooldown > 0.f || P.Think > 0.f) { return; }
		const int32 Rival = NearestOpponent(Index, 16.f * Yard, false);
		if (Rival == INDEX_NONE) { return; }
		const FFurySimPlayer& V = Players[Rival];
		const FVector2D To = V.P - P.P;
		if (To.SizeSquared() > FMath::Square(155.f))
		{
			Seek(P.P, V.P, P.TopSpeed * 0.72f, 0.f, OutWish, OutSpeed);
		}
		else if (V.Act == EFuryAct::Down)
		{
			StartElbow(Index, Rival);
			P.Think = RandRange(3.6f, 5.8f);
		}
		else if (!V.bDown)
		{
			StartStrike(Index, Chance(0.33f) ? EFuryAct::BigHit : EFuryAct::Shove, To.GetSafeNormal());
			P.Think = RandRange(3.6f, 5.8f);
		}
		return;
	}

	// Everything else: stroll to the huddle / the spot set for the next play.
	const FVector2D To = P.Home - P.P;
	if (To.SizeSquared() > 60.f * 60.f)
	{
		Seek(P.P, P.Home, P.TopSpeed * 0.55f, 200.f, OutWish, OutSpeed);
	}
	else if (P.Act != EFuryAct::Stand)
	{
		SetAct(P, EFuryAct::Stand, static_cast<uint8>(EFuryStance::Idle), 0.f, 0.f, false);
	}
	if (P.Act == EFuryAct::Stand && P.V.SizeSquared() > 60.f * 60.f)
	{
		SetAct(P, EFuryAct::Move, 0, 0.f, 0.f, false);
	}
}
