#include "FuryBot.h"

void FFuryBot::Reset(int32 InSeat, int32 Seed)
{
	Seat = InSeat;
	Random.Initialize(Seed + InSeat * 7919);
	Timer = 0.f;
	Hold = 0.f;
	LastPhase = EFuryPhase::GameOver;
	bPressedThisPhase = false;
}

FFurySeatInput FFuryBot::Think(const FFurySim& Sim, float Dt)
{
	FFurySeatInput In;
	const FFurySeat& Me = Sim.Seats[Seat];
	if (!Me.bActive)
	{
		return In;
	}
	if (Sim.Phase != LastPhase)
	{
		LastPhase = Sim.Phase;
		bPressedThisPhase = false;
		Timer = Random.FRandRange(0.5f, 1.4f);
		Hold = Random.FRandRange(1.1f, 2.6f);
		Weave = Random.FRandRange(0.f, 6.28f);
		bFreelance = Random.FRand() < 0.1f;
		// Decide up front which play to call, then steer the cursor there like a person would.
		WantCell = Random.RandRange(0, 8);
		WantPage = Random.FRand() < 0.72f ? 0 : 1;
		bWantFlip = Random.FRand() < 0.4f;
		if (Sim.Phase == EFuryPhase::PlaySelect && Me.Team == Sim.Offense && Sim.Captain(Me.Team) == Seat)
		{
			FFuryPick Kick;
			if (Sim.ChooseSituationalKick(Kick)) { WantPage = Kick.Page; WantCell = Kick.Cursor; bWantFlip = false; }
		}
	}
	Timer -= Dt;
	const bool bCaptain = Sim.Captain(Me.Team) == Seat;
	// Screen space: stick X is +X on the field, stick Y is -Y on the field.
	auto StickToward = [](const FVector2D& From, const FVector2D& To)
	{
		const FVector2D D = (To - From).GetSafeNormal();
		return FVector2D(D.X, -D.Y);
	};

	switch (Sim.Phase)
	{
	case EFuryPhase::PlaySelect:
		if (bCaptain && !Sim.Picks[Me.Team].bLocked && Timer <= 0.f)
		{
			const FFuryPick& Pick = Sim.Picks[Me.Team];
			const bool bOffense = Me.Team == Sim.Offense;
			const int32 Col = Pick.Cursor % 3, Row = Pick.Cursor / 3;
			if (bOffense && Pick.Page != WantPage) { In.RB = true; }
			else if (Col != WantCell % 3) { In.NavX = WantCell % 3 > Col ? 1 : -1; }
			else if (Row != WantCell / 3) { In.NavY = WantCell / 3 > Row ? -1 : 1; }
			else if (Pick.bFlip != bWantFlip) { In.X = true; }
			else { In.A = true; }
			Timer = Random.FRandRange(0.12f, 0.3f);
		}
		return In;

	case EFuryPhase::PatSelect:
		if (bCaptain && Timer <= 0.f)
		{
			if (!bPressedThisPhase && Random.FRand() < 0.2f) { In.NavX = 1; }
			else { In.A = true; }
			bPressedThisPhase = true;
			Timer = 0.4f;
		}
		return In;

	case EFuryPhase::PreSnap:
		if (bCaptain && Timer <= 0.f && Sim.PhaseTime > 0.5f)
		{
			In.A = true;
			Timer = 0.5f;
		}
		return In;

	default:
		break;
	}

	if (Me.Player == INDEX_NONE)
	{
		return In;
	}
	const FFurySimPlayer& P = Sim.Players[Me.Player];
	const float D = Fury::Dir(P.Team);

	if (Sim.AfterWhistle())
	{
		// Use the same buttons as a joined player. Space out attacks so a pile
		// breaks up naturally and follow the nearest opponent when they get up.
		In.A = Sim.ReadySeats != 0;  // yield to a person asking for the next play
		if (!P.Free() || Timer > 0.f) { return In; }
		const FFurySimPlayer* Rival = nullptr;
		float Best = FMath::Square(22.f * Fury::Yard);
		for (const FFurySimPlayer& Other : Sim.Players)
		{
			const float Dist = FVector2D::DistSquared(P.P, Other.P);
			if (P.Team != Other.Team && Dist < Best) { Best = Dist; Rival = &Other; }
		}
		if (!Rival) { return In; }
		In.Stick = StickToward(P.P, Rival->P);
		if (Best < FMath::Square(160.f) && P.Cooldown <= 0.f)
		{
			In.X = Rival->bDown || Random.FRand() < 0.32f;
			In.B = !In.X;
			In.bTurbo = In.B && Random.FRand() < 0.45f;
			Timer = Random.FRandRange(2.3f, 4.0f);
		}
		return In;
	}
	if (Sim.Phase != EFuryPhase::Live)
	{
		return In;
	}

	// The kick meter: stop it near the middle.
	if (Sim.bKickMeterLive && !Sim.bKickLocked && P.Job.Job == EFuryJob::Kicker)
	{
		if (FMath::Abs(Sim.KickMeter) < 0.16f)
		{
			In.A = true;
		}
		return In;
	}

	const int32 Carrier = Sim.CarrierIndex();
	if (P.bHasBall)
	{
		if (Sim.IsPasser(Me.Player))
		{
			// Hold it for a beat (or until someone gets close), then hit a receiver's button.
			float Nearest = 1.e9f;
			for (const FFurySimPlayer& O : Sim.Players)
			{
				if (O.Team != P.Team && !O.bDown)
				{
					Nearest = FMath::Min(Nearest, static_cast<float>(FVector2D::Distance(O.P, P.P)));
				}
			}
			if (Sim.LiveTime > Hold || Nearest < 260.f)
			{
				// Usually throw to whoever has the most room; sometimes just chuck it.
				int32 Icon = Random.RandRange(1, 3);
				if (Random.FRand() < 0.7f)
				{
					float Best = -1.f;
					for (int32 Slot = 0; Slot < Fury::TeamSize; ++Slot)
					{
						const FFurySimPlayer& R = Sim.Players[P.Team * Fury::TeamSize + Slot];
						if (R.PassIcon == 0 || R.bDown)
						{
							continue;
						}
						float Room = 1.e9f;
						for (const FFurySimPlayer& O : Sim.Players)
						{
							if (O.Team != P.Team && !O.bDown)
							{
								Room = FMath::Min(Room, static_cast<float>(FVector2D::Distance(O.P, R.P)));
							}
						}
						if (Room > Best)
						{
							Best = Room;
							Icon = R.PassIcon;
						}
					}
				}
				In.Y = Icon == 1;
				In.X = Icon == 2;
				In.A = Icon == 3;
				Hold = Sim.LiveTime + 0.3f;
			}
			return In;
		}
		// Run for the end zone with a weave, leaning on turbo, throwing in a move when crowded.
		Weave += Dt * 2.2f;
		FVector2D Wish(D, FMath::Sin(Weave) * 0.35f);
		if (FMath::Abs(P.P.Y) > Fury::SidelineY - 500.f)
		{
			Wish.Y = P.P.Y > 0.f ? -0.6f : 0.6f;
		}
		In.Stick = FVector2D(Wish.X, -Wish.Y).GetSafeNormal();
		In.bTurbo = true;
		if (Timer <= 0.f)
		{
			for (const FFurySimPlayer& O : Sim.Players)
			{
				if (O.Team != P.Team && !O.bDown && FVector2D::DistSquared(O.P, P.P) < 230.f * 230.f)
				{
					const float Roll = Random.FRand();
					In.A = Roll < 0.3f;
					In.B = Roll >= 0.3f && Roll < 0.6f;
					In.Y = Roll >= 0.6f && Roll < 0.75f;
					Timer = 0.9f;
					break;
				}
			}
		}
		return In;
	}

	const bool bMyBall = Sim.BallTeam == P.Team && Sim.Ball.State != EFuryBallState::Loose;
	if (bMyBall)
	{
		// Offense without the ball: mostly let the route run itself; go up for a pass thrown my way.
		if (Sim.Ball.State == EFuryBallState::Pass && Sim.Ball.Target == Me.Player)
		{
			In.Stick = StickToward(P.P, Sim.Ball.Land());
			In.bTurbo = true;
			if (Sim.Ball.Duration - Sim.Ball.Time < 0.3f) { In.Y = true; }
		}
		return In;
	}

	// Defense. While the quarterback still has it, a sensible player stays on their assignment
	// (hands off the stick lets the athlete cover by himself); now and then they freelance and blitz.
	if (Carrier != INDEX_NONE && Sim.IsPasser(Carrier) && !bFreelance)
	{
		const bool bCovering = P.Job.Job == EFuryJob::Man || P.Job.Job == EFuryJob::Zone || P.Job.Job == EFuryJob::Spy;
		if (bCovering)
		{
			return In;
		}
	}
	// Otherwise: chase the ball, dive when close, switch if someone else is better placed.
	FVector2D Goal(Sim.Ball.Pos.X, Sim.Ball.Pos.Y);
	if (Carrier != INDEX_NONE)
	{
		Goal = Sim.Players[Carrier].P + Sim.Players[Carrier].V * 0.3f;
	}
	else if (Sim.Ball.State == EFuryBallState::Pass || Sim.Ball.State == EFuryBallState::Kick)
	{
		Goal = Sim.Ball.Land();
	}
	In.Stick = StickToward(P.P, Goal);
	In.bTurbo = true;
	const float Dist = FVector2D::Distance(P.P, Goal);
	if (Timer <= 0.f)
	{
		if (Carrier != INDEX_NONE && Dist < 185.f && Dist > 105.f)
		{
			// Close enough to finish it: usually just run through him, sometimes leave the feet or unload.
			const float Roll = Random.FRand();
			In.X = Roll < 0.3f;
			In.B = Roll >= 0.3f && Roll < 0.5f;
			Timer = 0.8f;
		}
		else if (Sim.Ball.State == EFuryBallState::Pass && Dist < 200.f && Sim.Ball.Duration - Sim.Ball.Time < 0.3f)
		{
			In.Y = true;
			Timer = 0.8f;
		}
		else if (Dist > 1100.f)
		{
			In.A = true;      // somebody else is closer
			Timer = 0.7f;
		}
	}
	return In;
}
