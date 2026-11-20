#include "FuryPlaybook.h"

namespace
{
	using FPath = TArray<FVector2D>;

	// --- Offensive building blocks -------------------------------------------------------------
	const FVector2D QBSpot(-5.f, 0.f);
	const FVector2D CenterSpot(-0.4f, 0.f), LeftGuardSpot(-0.5f, -1.8f), RightGuardSpot(-0.5f, 1.8f);
	// Receivers split a little tighter than on a real field: it keeps the whole formation big on screen.
	const FVector2D WideLeft(-0.6f, -13.f), WideRight(-0.6f, 13.f);
	const FVector2D BackRight(-5.f, 2.4f), BackLeft(-5.f, -2.4f), SlotRight(-1.f, 7.f), SlotLeft(-1.f, -7.f), TightRight(-0.5f, 3.9f);

	FFuryJobSpec Passer(FPath Rollout = {})
	{
		FFuryJobSpec Spec;
		Spec.Job = EFuryJob::Passer;
		Spec.Path = MoveTemp(Rollout);
		return Spec;
	}
	FFuryJobSpec PassBlock() { FFuryJobSpec Spec; Spec.Job = EFuryJob::PassBlock; return Spec; }
	FFuryJobSpec RunBlock() { FFuryJobSpec Spec; Spec.Job = EFuryJob::RunBlock; return Spec; }
	/** A route for a split receiver: Y is toward the middle of the field. */
	FFuryJobSpec Route(FPath Path, float Delay = 0.f)
	{
		FFuryJobSpec Spec;
		Spec.Job = EFuryJob::Route;
		Spec.Path = MoveTemp(Path);
		Spec.bInward = true;
		Spec.Delay = Delay;
		return Spec;
	}
	/** A route in plain play space (Y toward the offense's right), for backs and slots. */
	FFuryJobSpec BackRoute(FPath Path, float Delay = 0.f)
	{
		FFuryJobSpec Spec = Route(MoveTemp(Path), Delay);
		Spec.bInward = false;
		return Spec;
	}
	FFuryJobSpec Carry(FPath Path) { FFuryJobSpec Spec; Spec.Job = EFuryJob::Carry; Spec.Path = MoveTemp(Path); return Spec; }
	FFuryJobSpec Keeper(FPath Path) { FFuryJobSpec Spec; Spec.Job = EFuryJob::Keeper; Spec.Path = MoveTemp(Path); return Spec; }

	// Common routes for split receivers (depth, toward the middle).
	FPath Go() { return { { 45.f, 0.f } }; }
	FPath Slant() { return { { 2.f, 0.f }, { 10.f, 8.f }, { 24.f, 22.f } }; }
	FPath Curl() { return { { 13.f, 0.f }, { 11.f, 1.5f } }; }
	FPath Hitch() { return { { 6.f, 0.f }, { 5.f, 1.f } }; }
	FPath Out() { return { { 12.f, 0.f }, { 12.5f, -9.f } }; }
	FPath Post() { return { { 13.f, 0.f }, { 38.f, 13.f } }; }
	FPath Corner() { return { { 12.f, 0.f }, { 30.f, -9.f } }; }
	FPath Dig() { return { { 14.f, 0.f }, { 15.f, 16.f } }; }
	FPath Comeback() { return { { 16.f, 0.f }, { 12.f, -3.f } }; }
	FPath Drag(float Depth) { return { { Depth - 1.f, 0.f }, { Depth, 30.f } }; }
	FPath DeepOver() { return { { 10.f, 0.f }, { 19.f, 30.f } }; }

	FFuryOffPlay Offense(const TCHAR* Name, const TCHAR* Tagline, EFuryPlayKind Kind, FVector2D BackSpot,
		FFuryJobSpec QB, FFuryJobSpec Left, FFuryJobSpec Right, FFuryJobSpec Back, int32 Primary, float Drop = 3.f)
	{
		FFuryOffPlay Play;
		Play.Name = Name;
		Play.Tagline = Tagline;
		Play.Kind = Kind;
		Play.Spot[0] = QBSpot; Play.Spot[1] = CenterSpot; Play.Spot[2] = LeftGuardSpot; Play.Spot[3] = RightGuardSpot;
		Play.Spot[4] = WideLeft; Play.Spot[5] = WideRight; Play.Spot[6] = BackSpot;
		Play.Job[0] = MoveTemp(QB);
		const bool bRun = Kind == EFuryPlayKind::Run;
		Play.Job[1] = Play.Job[2] = Play.Job[3] = bRun ? RunBlock() : PassBlock();
		Play.Job[4] = MoveTemp(Left);
		Play.Job[5] = MoveTemp(Right);
		Play.Job[6] = MoveTemp(Back);
		Play.Primary = Primary;
		Play.Drop = Drop;
		return Play;
	}

	// --- Defensive building blocks -------------------------------------------------------------
	const FVector2D EndLeft(0.9f, -2.6f), Tackle(0.9f, 0.f), EndRight(0.9f, 2.6f), Backer(4.5f, 0.f), Deep(14.f, 0.f);

	FFuryJobSpec Rush() { FFuryJobSpec Spec; Spec.Job = EFuryJob::Rush; return Spec; }
	FFuryJobSpec Blitz(float Delay) { FFuryJobSpec Spec; Spec.Job = EFuryJob::Blitz; Spec.Delay = Delay; return Spec; }
	FFuryJobSpec Man(int32 Target, float Cushion, bool bPress = false)
	{
		FFuryJobSpec Spec;
		Spec.Job = EFuryJob::Man;
		Spec.Target = Target;
		Spec.Cushion = Cushion;
		Spec.bPress = bPress;
		return Spec;
	}
	FFuryJobSpec Zone(float Depth, float Lateral, float Radius)
	{
		FFuryJobSpec Spec;
		Spec.Job = EFuryJob::Zone;
		Spec.Zone = FVector2D(Depth, Lateral);
		Spec.Radius = Radius;
		return Spec;
	}
	FFuryJobSpec Spy() { FFuryJobSpec Spec; Spec.Job = EFuryJob::Spy; return Spec; }

	FFuryDefPlay Defense(const TCHAR* Name, const TCHAR* Tagline, FFuryJobSpec E1, FFuryJobSpec T, FFuryJobSpec E2,
		FFuryJobSpec LB, FFuryJobSpec CornerLeft, FFuryJobSpec CornerRight, FFuryJobSpec Safety)
	{
		FFuryDefPlay Play;
		Play.Name = Name;
		Play.Tagline = Tagline;
		Play.Spot[0] = EndLeft; Play.Spot[1] = Tackle; Play.Spot[2] = EndRight; Play.Spot[3] = Backer;
		// Corners line up over their receivers; these are only fallbacks. Zone players start in their zone.
		Play.Spot[4] = FVector2D(5.f, -13.f); Play.Spot[5] = FVector2D(5.f, 13.f); Play.Spot[6] = Deep;
		Play.Job[0] = MoveTemp(E1); Play.Job[1] = MoveTemp(T); Play.Job[2] = MoveTemp(E2);
		Play.Job[3] = MoveTemp(LB); Play.Job[4] = MoveTemp(CornerLeft); Play.Job[5] = MoveTemp(CornerRight); Play.Job[6] = MoveTemp(Safety);
		for (int32 i = 3; i < 7; ++i)
		{
			if (Play.Job[i].Job == EFuryJob::Zone)
			{
				Play.Spot[i] = Play.Job[i].Zone;
			}
			else if (Play.Job[i].Job == EFuryJob::Blitz)
			{
				// Blitzers creep toward the line so the rush actually gets home (and do not stack up).
				float Lateral = Play.Spot[i].Y * 0.45f;
				if (FMath::Abs(Lateral) < 0.5f)
				{
					Lateral = i == 3 ? -1.3f : 3.4f;
				}
				Play.Spot[i] = FVector2D(FMath::Min(Play.Spot[i].X, 3.f), Lateral);
			}
		}
		return Play;
	}
}

const TArray<FFuryOffPlay>& FuryPlaybook::Offense()
{
	static const TArray<FFuryOffPlay> Plays = []
	{
		TArray<FFuryOffPlay> P;

		// ---- Page 1: the passing game -------------------------------------------------------
		P.Add(::Offense(TEXT("SKYLINE"), TEXT("Three go deep. Pick one."), EFuryPlayKind::Pass, BackRight,
			Passer(), Route(Go()), Route(Go()), BackRoute({ { 1.f, 6.f }, { 5.f, 9.f }, { 40.f, 9.f } }), 5, 4.f));
		P.Add(::Offense(TEXT("CROSSFIRE"), TEXT("Two crossers and a flat. Hit the gap."), EFuryPlayKind::Pass, BackLeft,
			Passer(), Route(Drag(5.f)), Route(Dig()), BackRoute({ { 1.f, -7.f }, { 2.5f, -14.f } }), 4));
		P.Add(::Offense(TEXT("OUT RAGE"), TEXT("Sideline outs with a seam up the gut."), EFuryPlayKind::Pass, BackRight,
			Passer(), Route(Out()), Route(Out()), BackRoute({ { 8.f, -2.2f }, { 38.f, -2.2f } }), 5));
		P.Add(::Offense(TEXT("SLANT STORM"), TEXT("Quick slants. Get it out fast."), EFuryPlayKind::Pass, BackRight,
			Passer(), Route(Slant()), Route(Slant()), BackRoute({ { -1.f, 6.f }, { 1.f, 12.f }, { 9.f, 14.f } }), 5, 1.5f));
		P.Add(::Offense(TEXT("CURL UP"), TEXT("Sit down at the sticks."), EFuryPlayKind::Pass, BackRight,
			Passer(), Route(Curl()), Route(Curl()), BackRoute({ { 5.f, -2.f }, { 7.f, -2.4f } }), 4));
		P.Add(::Offense(TEXT("POST MASTER"), TEXT("Post and corner split the safety."), EFuryPlayKind::Pass, BackRight,
			Passer(), Route(Post()), Route(Corner()), BackRoute({ { 2.f, -3.f }, { 4.f, -16.f } }), 4, 4.f));
		P.Add(::Offense(TEXT("FLOOD RIGHT"), TEXT("Three levels down one sideline."), EFuryPlayKind::Pass, SlotRight,
			Passer(), Route(DeepOver()), Route(Go()), BackRoute({ { 7.f, 0.f }, { 7.5f, 9.f } }), 6));
		P.Add(::Offense(TEXT("DAGGER"), TEXT("Clear it out, then dig underneath."), EFuryPlayKind::Pass, SlotRight,
			Passer(), Route(Comeback()), Route(Dig()), BackRoute({ { 42.f, 1.f } }), 5, 4.f));
		P.Add(::Offense(TEXT("HAIL FURY"), TEXT("Everybody long. Pray."), EFuryPlayKind::Pass, SlotLeft,
			Passer(), Route({ { 48.f, 3.f } }), Route({ { 48.f, 3.f } }), BackRoute({ { 46.f, 4.f } }), 5, 5.f));

		// ---- Page 2: quick game, runs and tricks ---------------------------------------------
		P.Add(::Offense(TEXT("QUICK HITCH"), TEXT("Five yards, right now."), EFuryPlayKind::Pass, BackRight,
			Passer(), Route(Hitch()), Route(Hitch()), BackRoute({ { 0.f, 6.f }, { 2.f, 13.f } }), 4, 1.5f));
		P.Add(::Offense(TEXT("MESH"), TEXT("Drags rub the defenders off."), EFuryPlayKind::Pass, BackRight,
			Passer(), Route(Drag(5.f)), Route(Drag(4.f)), BackRoute({ { 4.f, 4.f }, { 10.f, 6.f }, { 26.f, 15.f } }), 4));
		{
			FFuryOffPlay Play = ::Offense(TEXT("SCREEN DOOR"), TEXT("Let them come. Then dump it off."), EFuryPlayKind::Pass, BackLeft,
				Passer(), Route(Go()), Route(Go()), BackRoute({ { -0.5f, -5.f }, { -1.5f, -9.f } }, 0.5f), 6, 5.f);
			Play.bScreen = true;
			P.Add(MoveTemp(Play));
		}
		P.Add(::Offense(TEXT("THUNDER DIVE"), TEXT("Hand it off and hit the hole."), EFuryPlayKind::Run, BackRight,
			Passer(), RunBlock(), RunBlock(), Carry({ { 0.7f, -1.5f }, { 5.5f, -1.4f }, { 16.f, -1.8f } }), 6));
		P.Add(::Offense(TEXT("SWEEP"), TEXT("Toss it wide and turn the corner."), EFuryPlayKind::Run, BackLeft,
			Passer(), RunBlock(), RunBlock(), Carry({ { 0.2f, 3.6f }, { 0.f, 13.f }, { 5.f, 18.f }, { 30.f, 19.f } }), 6));
		P.Add(::Offense(TEXT("COUNTER PUNCH"), TEXT("Show right, cut back left."), EFuryPlayKind::Run, BackRight,
			Passer(), RunBlock(), RunBlock(), Carry({ { 0.6f, -2.6f }, { 5.f, -5.f }, { 16.f, -7.f } }), 6));
		P.Add(::Offense(TEXT("QB DRAW"), TEXT("Fake the drop. Take off."), EFuryPlayKind::Run, BackRight,
			Keeper({ { -1.f, 0.4f }, { 1.5f, 2.5f }, { 8.f, 2.8f }, { 22.f, 2.f } }), Route(Go()), Route(Go()), RunBlock(), 0));
		P.Add(::Offense(TEXT("BOOTLEG"), TEXT("Roll right. Run it or throw it."), EFuryPlayKind::Pass, BackRight,
			Passer({ { -2.f, 6.f }, { -1.f, 11.f } }), Route(DeepOver()), Route(Comeback()), BackRoute({ { 1.f, 6.f }, { 3.f, 13.f } }), 5, 0.f));
		{
			FFuryOffPlay Play = ::Offense(TEXT("PLAY ACTION"), TEXT("Sell the run. Throw the bomb."), EFuryPlayKind::Pass, BackRight,
				Passer(), Route(Post()), Route(Go()), BackRoute({ { 0.7f, -1.5f }, { 4.f, -1.4f } }), 4, 4.f);
			Play.bPlayAction = true;
			P.Add(MoveTemp(Play));
		}
		return P;
	}();
	return Plays;
}

const FFuryOffPlay& FuryPlaybook::Punt()
{
	static const FFuryOffPlay Play = []
	{
		FFuryOffPlay P;
		P.Name = TEXT("PUNT");
		P.Tagline = TEXT("Flip the field.");
		P.Kind = EFuryPlayKind::Punt;
		P.Spot[0] = FVector2D(-13.f, 0.f);
		P.Spot[1] = CenterSpot; P.Spot[2] = LeftGuardSpot; P.Spot[3] = RightGuardSpot;
		P.Spot[4] = FVector2D(-0.6f, -9.f); P.Spot[5] = FVector2D(-0.6f, 9.f); P.Spot[6] = FVector2D(-6.f, 2.5f);
		P.Job[0].Job = EFuryJob::Punter;
		P.Job[1] = P.Job[2] = P.Job[3] = PassBlock();
		for (int32 i = 4; i < 6; ++i) { P.Job[i].Job = EFuryJob::Cover; }
		P.Job[6] = PassBlock();
		P.Primary = 0;
		return P;
	}();
	return Play;
}

const FFuryOffPlay& FuryPlaybook::FieldGoal()
{
	static const FFuryOffPlay Play = []
	{
		FFuryOffPlay P;
		P.Name = TEXT("FIELD GOAL");
		P.Tagline = TEXT("Three points. Probably.");
		P.Kind = EFuryPlayKind::FieldGoal;
		P.Spot[0] = FVector2D(-9.5f, -1.6f);                    // kicker
		P.Spot[1] = CenterSpot; P.Spot[2] = LeftGuardSpot; P.Spot[3] = RightGuardSpot;
		P.Spot[4] = FVector2D(-0.6f, -3.7f); P.Spot[5] = FVector2D(-0.6f, 3.7f);   // wings
		P.Spot[6] = FVector2D(-7.f, 0.6f);                      // holder
		P.Job[0].Job = EFuryJob::Kicker;
		for (int32 i = 1; i < 6; ++i) { P.Job[i] = PassBlock(); }
		P.Job[6].Job = EFuryJob::Holder;
		P.Primary = 0;
		return P;
	}();
	return Play;
}

const TArray<FFuryDefPlay>& FuryPlaybook::Defense()
{
	static const TArray<FFuryDefPlay> Plays = []
	{
		TArray<FFuryDefPlay> P;
		P.Add(::Defense(TEXT("ALL-OUT FURY"), TEXT("Send the house."),
			Rush(), Rush(), Rush(), Blitz(0.f), Man(4, 3.f), Man(5, 3.f), Blitz(0.25f)));
		P.Add(::Defense(TEXT("PRESS MAN"), TEXT("Jam them at the line."),
			Rush(), Rush(), Rush(), Man(6, 3.f), Man(4, 1.3f, true), Man(5, 1.3f, true), Zone(13.f, 0.f, 14.f)));
		P.Add(::Defense(TEXT("ZONE BLANKET"), TEXT("Three deep. Nothing over the top."),
			Rush(), Rush(), Rush(), Zone(6.f, 0.f, 9.f), Zone(15.f, -13.f, 11.f), Zone(15.f, 13.f, 11.f), Zone(18.f, 0.f, 11.f)));
		P.Add(::Defense(TEXT("PICKET FENCE"), TEXT("Take away everything short."),
			Rush(), Rush(), Rush(), Zone(5.f, 0.f, 7.f), Zone(5.5f, -11.f, 7.5f), Zone(5.5f, 11.f, 7.5f), Zone(13.f, 0.f, 13.f)));
		P.Add(::Defense(TEXT("BASE MAN"), TEXT("Everyone has a man. Safety roams."),
			Rush(), Rush(), Rush(), Man(6, 4.f), Man(4, 5.f), Man(5, 5.f), Zone(15.f, 0.f, 14.f)));
		P.Add(::Defense(TEXT("CORNER FIRE"), TEXT("The corner comes off the edge."),
			Rush(), Rush(), Rush(), Man(6, 4.f), Man(4, 5.f), Blitz(0.f), Man(5, 8.f)));
		P.Add(::Defense(TEXT("SPY GAME"), TEXT("Shadow the quarterback."),
			Rush(), Rush(), Rush(), Spy(), Man(4, 5.f), Man(5, 5.f), Zone(13.f, 0.f, 14.f)));
		P.Add(::Defense(TEXT("DOUBLE TROUBLE"), TEXT("Two bodies on their left receiver."),
			Rush(), Rush(), Rush(), Man(6, 4.f), Man(4, 2.5f), Man(5, 5.f), Man(4, 10.f)));
		P.Add(::Defense(TEXT("PREVENT WALL"), TEXT("Rush two. Guard the end zone."),
			Rush(), Zone(4.f, 0.f, 6.f), Rush(), Zone(10.f, 0.f, 9.f), Zone(20.f, -12.f, 12.f), Zone(20.f, 12.f, 12.f), Zone(27.f, 0.f, 14.f)));
		return P;
	}();
	return Plays;
}

const FFuryDefPlay& FuryPlaybook::KickBlock()
{
	static const FFuryDefPlay Play = []
	{
		FFuryDefPlay P = ::Defense(TEXT("KICK BLOCK"), TEXT(""),
			Rush(), Rush(), Rush(), Rush(), FFuryJobSpec(), FFuryJobSpec(), FFuryJobSpec());
		P.Spot[3] = FVector2D(0.9f, 4.6f);
		P.Spot[4] = FVector2D(3.f, -9.f); P.Spot[5] = FVector2D(3.f, 9.f); P.Spot[6] = FVector2D(42.f, 0.f);
		P.Job[4].Job = EFuryJob::ReturnBlock; P.Job[5].Job = EFuryJob::ReturnBlock;
		P.Job[6].Job = EFuryJob::Returner;
		return P;
	}();
	return Play;
}

FFuryOffPlay FuryPlaybook::Flip(const FFuryOffPlay& Play)
{
	FFuryOffPlay Out = Play;
	for (int32 i = 0; i < 7; ++i)
	{
		Out.Spot[i].Y = -Out.Spot[i].Y;
		if (!Out.Job[i].bInward)
		{
			for (FVector2D& Point : Out.Job[i].Path)
			{
				Point.Y = -Point.Y;
			}
		}
	}
	return Out;
}

FFuryDefPlay FuryPlaybook::Flip(const FFuryDefPlay& Play)
{
	FFuryDefPlay Out = Play;
	for (int32 i = 0; i < 7; ++i)
	{
		Out.Spot[i].Y = -Out.Spot[i].Y;
		Out.Job[i].Zone.Y = -Out.Job[i].Zone.Y;
		// Man assignments on the split receivers swap sides with the picture.
		if (Out.Job[i].Job == EFuryJob::Man && (Out.Job[i].Target == 4 || Out.Job[i].Target == 5))
		{
			Out.Job[i].Target = 9 - Out.Job[i].Target;
		}
	}
	return Out;
}
