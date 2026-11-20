#pragma once

#include "CoreMinimal.h"
#include "FuryPlaybook.h"
#include "FuryTeams.h"
#include "FuryTypes.h"

/**
 * The football itself: rules, movement, contact, the ball, and the computer players' brains.
 *
 * It is plain C++ with no engine objects, stepped with a fixed or variable time step, so a whole
 * match can be played without rendering (see -FurySimTest). The director feeds it the human
 * players' input, then reads its state to drive athletes, camera, sound and interface.
 */

enum class EFuryPhase : uint8
{
	PlaySelect,    // both sides choose a play
	Lineup,        // players jog to their spots
	PreSnap,       // set, waiting for the snap or the kick
	Live,          // ball in play
	Dead,          // whistle has gone; the after-whistle window
	Celebrate,     // touchdown party
	PatSelect,     // scoring side chooses: kick the extra point or go for two
	Break,         // end of a quarter, halftime
	GameOver,
};

enum class EFuryPlayType : uint8 { Scrimmage, Kickoff, Punt, FieldGoal, ExtraPoint, TwoPoint };

enum class EFuryBallState : uint8
{
	Held,      // in a player's hands
	Snap,      // travelling from the centre to the backfield
	Pass,      // thrown; can be caught, tipped or intercepted
	Kick,      // kickoff or punt in the air
	FieldGoal, // heading for the uprights
	Loose,     // fumbled or bouncing: anyone's ball
	Tee,       // sitting on the tee / ground before a kick
	Dead,
};

enum class EFuryEvent : uint8
{
	PlayStart, Snap, Hut, Throw, Pitch, Handoff, Catch, Drop, Incomplete, Tip, Intercept,
	Tackle, BigHit, Sack, Fumble, Recover, BrokenTackle, StiffArm, Spin, Juke, Hurdle, Dive, DiveMiss, Shove, Pancake, LateHit,
	Touchdown, FirstDown, TurnoverOnDowns, Safety, Touchback, OutOfBounds, Whistle,
	Kickoff, PuntKick, FieldGoalKick, FieldGoalGood, FieldGoalNoGood, ExtraPointGood, ExtraPointNoGood, TwoPointGood, TwoPointNoGood, Doink,
	FuryStart, FuryEnd, PlayPicked, QuarterEnd, Halftime, Overtime, GameOver, TwoMinute,
};

struct FFuryEvent
{
	EFuryEvent Type;
	int32 Team = INDEX_NONE;
	int32 Player = INDEX_NONE;   // global player index (0..13)
	int32 Other = INDEX_NONE;
	FVector Pos = FVector::ZeroVector;
	float Value = 0.f;
};

/** One human's input for a step. Stick is screen-relative: X right, Y up. */
struct FFurySeatInput
{
	FVector2D Stick = FVector2D::ZeroVector;
	bool bTurbo = false;
	bool A = false, B = false, X = false, Y = false;   // pressed this step
	bool LB = false, RB = false;
	int32 NavX = 0, NavY = 0;
};

struct FFurySeat
{
	bool bActive = false;
	int32 Team = 0;
	int32 Player = INDEX_NONE;   // global index of the athlete this human controls
	float Turbo = 1.f;
	bool bTurboSpent = false;
	float Idle = 0.f;            // seconds since this human last touched the stick
	// For the post-game sheet
	int32 Tackles = 0, Touchdowns = 0, Sacks = 0, Picks = 0, BigHits = 0;
};

struct FFurySimPlayer
{
	// Identity
	int32 Team = 0;
	int32 Slot = 0;              // 0..6 within the unit on the field
	int32 Roster = 0;            // index into the team's roster (name, number, build)
	EFuryPos Pos = EFuryPos::WR;
	float TopSpeed = 760.f, Power = 0.5f, Hands = 0.9f, Radius = 42.f;

	// Kinematics
	FVector2D P = FVector2D::ZeroVector, V = FVector2D::ZeroVector;
	float Yaw = 0.f;
	float Height = 0.f;          // lift for launches; jumps live in the animation

	// What the athlete is doing
	EFuryAct Act = EFuryAct::Stand;
	uint8 Variant = 0;
	int32 ActSerial = 0;
	float ActTime = 0.f;
	float ActLength = 0.f;       // 0 = open-ended
	float ActKey = 0.f;          // moment within the action that matters (release, contact)
	bool bBusy = false;          // cannot steer until the action ends
	bool bKeyDone = false;
	bool bDiveSpent = false;         // one collision or evasion contest per dive

	// Status
	bool bHasBall = false;
	bool bDown = false;          // on the ground
	float DownLeft = 0.f;        // seconds until getting up
	float EvadeLeft = 0.f;       // spin / hurdle window: tackles miss
	float StiffLeft = 0.f;       // stiff-arm window
	float Cooldown = 0.f;        // special move cooldown
	float CatchCool = 0.f;       // cannot try for the ball again until this runs out
	float JumpLeft = 0.f;        // leaping for the ball: extra reach
	float Burst = 0.f;           // seconds of extra speed left (computer players)
	float BurstCool = 0.f;       // seconds until a computer player can burst again
	int32 Engaged = INDEX_NONE;  // global index of the player locked up with
	float EngageTime = 0.f, ShedAt = 0.f;
	bool bBlocker = false;       // in an engagement: true for the blocking side
	int32 Seat = INDEX_NONE;     // human in control, if any
	FVector2D Launch = FVector2D::ZeroVector;   // velocity while flying from a hit or a dive
	bool bFace = false;          // face FaceYaw this step instead of the direction of travel
	float FaceYaw = 0.f;
	bool bScramble = false;      // quarterback has given up on the pocket
	bool bPursue = false;        // defender has read "run" (or a catch) and is chasing the ball
	float ReadLeft = -1.f;       // seconds until that read sinks in (-1 = nothing to read yet)

	// Assignment
	FFuryJobSpec Job;
	TArray<FVector2D> Path;      // world waypoints
	int32 PathIndex = 0;
	FVector2D Home = FVector2D::ZeroVector;
	int32 Mark = INDEX_NONE;     // global index: man to cover / block / chase
	float React = 0.f;           // reaction delay left
	float Think = 0.f;           // decision timer
	bool bRouteDone = false;
	bool bBroke = false;         // defender has reacted to the throw
	uint8 PassIcon = 0;          // 0 none, 1 Y (top of screen), 2 X/B (middle), 3 A (bottom)

	bool Free() const { return !bDown && !bBusy && Engaged == INDEX_NONE; }
	bool Upright() const { return !bDown; }
};

struct FFuryBall
{
	EFuryBallState State = EFuryBallState::Dead;
	FVector Pos = FVector::ZeroVector, Vel = FVector::ZeroVector;
	int32 Holder = INDEX_NONE;       // global player index
	int32 Target = INDEX_NONE;       // intended receiver
	int32 Thrower = INDEX_NONE;
	FVector From = FVector::ZeroVector, To = FVector::ZeroVector;
	float Time = 0.f, Duration = 0.f;
	bool bTipped = false;
	bool bArrived = false;           // the contest at the catch point has been held
	bool bKickGood = false;
	float Spin = 0.f;
	FVector2D Land() const { return FVector2D(To.X, To.Y); }
};

struct FFuryPick
{
	int32 Page = 0;
	int32 Cursor = 4;
	bool bFlip = false;
	bool bLocked = false;
	int32 Play = INDEX_NONE;     // index into the offense or defense list; -2 punt, -3 field goal
	float CpuDelay = 0.f;
};

struct FFuryTeamState
{
	int32 League = 0;            // index into Fury::Teams()
	int32 Score = 0;
	float Fury = 0.f;            // meter, 0..1
	int32 FuryPlays = 0;         // plays of Fury mode left
	int32 Completions = 0, Attempts = 0, PassYards = 0, RushYards = 0, Sacks = 0, Picks = 0, FumblesLost = 0, FirstDowns = 0, BigHits = 0, Touchdowns = 0;
	int32 ScoreByQuarter[5] = {};
	int32 LongestTD = -1, LongestScorer = INDEX_NONE;
	FString LongestType;
	bool bHuman = false;
	bool InFury() const { return FuryPlays > 0; }
};

class FFurySim
{
public:
	// --- Setup ---
	void StartMatch(int32 HomeLeague, int32 AwayLeague, float QuarterSeconds, float InCpuSkill, int32 Seed);
	void SetSeat(int32 Index, bool bActive, int32 Team);

	// --- Step ---
	void Step(float Dt, const FFurySeatInput* Inputs);

	/** Test hook: jump straight to a field-goal try by NewOffense from the given yard line (0..100 from its own goal). */
	void DebugFieldGoal(int32 NewOffense, float YardsFromOwnGoal);

	// --- Queries for presentation ---
	const FFuryTeam& TeamInfo(int32 Team) const { return Fury::Teams()[Teams[Team].League]; }
	const FFuryRosterEntry& RosterOf(const FFurySimPlayer& Player) const { return TeamInfo(Player.Team).Roster[Player.Roster]; }
	float OffenseDir() const { return Fury::Dir(Offense); }
	int32 Defense() const { return 1 - Offense; }
	float YardsToGo() const;
	float FieldGoalYards() const { return FMath::Abs(OffenseDir() * Fury::EndLineX - LosX) / Fury::Yard + 7.f; }
	static constexpr float AfterWhistleSeconds = 3.f;
	bool AfterWhistle() const { return Phase == EFuryPhase::Dead || Phase == EFuryPhase::Celebrate; }
	FVector2D WhistleFocus = FVector2D::ZeroVector;
	uint8 ReadySeats = 0;          // joined seats that voted for the next play
	static constexpr float MaxKickYards = 61.f;
	static constexpr float UprightHalfWidth = 282.f;
	static constexpr float CleanKickWidth = UprightHalfWidth - 18.f;
	static constexpr float KickScatter = 35.f;
	static float KickSpread(float Yards) { return 250.f + 14.f * Yards; }
	bool GoalToGo() const;
	/** "2ND & 14", "1ST & GOAL", "KICKOFF". */
	FString DownText() const;
	/** "OWN 35", "OPP 12", "50". */
	FString SpotText() const;
	FString ClockText() const;
	const FFuryOffPlay* OffensePlay() const { return bHaveOffPlay ? &CurrentOff : nullptr; }
	const FFuryDefPlay* DefensePlay() const { return bHaveDefPlay ? &CurrentDef : nullptr; }
	/** The offense choices on a pick page (regular pages, then the kicking page). */
	int32 NumOffensePages() const { return 3; }
	const FFuryOffPlay* OffenseChoice(int32 Page, int32 Cell) const;
	const FFuryDefPlay* DefenseChoice(int32 Cell) const;
	/** Set a kick call when distance, score and time favor special teams. */
	bool ChooseSituationalKick(FFuryPick& Pick) const;
	int32 Captain(int32 Team) const;       // seat index calling plays for a team, or INDEX_NONE (computer)
	bool IsPassIconLive() const;
	/** True while this athlete is a quarterback holding the ball behind the line, able to throw. */
	bool IsPasser(int32 Index) const;
	int32 CarrierIndex() const { return Ball.State == EFuryBallState::Held ? Ball.Holder : INDEX_NONE; }
	FVector2D BallSpot() const { return FVector2D(LosX, BallY); }
	int32 Winner() const;

	// --- State ---
	EFuryPhase Phase = EFuryPhase::GameOver;
	float PhaseTime = 0.f;
	EFuryPlayType PlayType = EFuryPlayType::Kickoff;
	int32 Quarter = 1;
	float Clock = 120.f, QuarterLength = 120.f;
	int32 Offense = 0;             // team snapping / the team that will have the ball after a kick
	int32 BallTeam = 0;            // team in possession right now
	int32 KickingTeam = 0;
	int32 Down = 1;
	float LosX = 0.f, FirstDownX = 0.f, BallY = 0.f;
	float LiveTime = 0.f;
	float CpuSkill = 0.5f;
	int32 PlayCount = 0, DriveCount = 0;
	bool bOvertime = false;

	FFurySimPlayer Players[Fury::NumPlayers];
	FFuryBall Ball;
	FFuryTeamState Teams[2];
	FFurySeat Seats[Fury::MaxSeats];
	FFuryPick Picks[2];
	int32 PatChoice = 0;           // 0 kick, 1 go for two
	float SelectTimer = 0.f;

	// Kick meter (field goals and extra points): swings -1..1; locked when the kicker commits.
	float KickMeter = 0.f, KickAim = 0.f;
	bool bKickMeterLive = false, bKickLocked = false;
	FVector2D KickSteer = FVector2D::ZeroVector;

	// Result of the last play, for banners.
	FString ResultTitle, ResultDetail;
	int32 ResultTeam = INDEX_NONE;
	float PlayYards = 0.f;
	int32 ScoringTeam = INDEX_NONE;
	int32 Scorer = INDEX_NONE;

	TArray<FFuryEvent> Events;

	// Counters for the balance test (-FurySimTest); they have no effect on play.
	int32 Tally[12] = {};

private:
	// Flow (FurySim.cpp)
	void Emit(EFuryEvent Type, int32 Team = INDEX_NONE, int32 Player = INDEX_NONE, int32 Other = INDEX_NONE, float Value = 0.f);
	void Enter(EFuryPhase NewPhase);
	void BeginKickoff(int32 Kicker, float FromYard);
	void BeginScrimmage(int32 NewOffense, float NewLosX, float NewBallY, bool bFirstDown);
	void BeginPlaySelect();
	void StepPlaySelect(float Dt, const FFurySeatInput* Inputs);
	void StepPatSelect(float Dt, const FFurySeatInput* Inputs);
	void CpuPickOffense(FFuryPick& Pick);
	void CpuPickDefense(FFuryPick& Pick);
	void SetupPlay();
	void SetupKickoff();
	void PlaceUnits(bool bOffenseUnit[2]);
	void AssignSeats();
	void StepLineup(float Dt);
	void StepPreSnap(float Dt, const FFurySeatInput* Inputs);
	void SnapBall();
	void BeginAfterWhistle(EFuryPhase NewPhase, FVector2D Spot);
	void StepAfterWhistle(const FFurySeatInput* Inputs);
	void FinishCelebration();
	void StepBreak(float Dt);
	void EndPlay(const TCHAR* Title, const FString& Detail, int32 Team);
	void ResolveDown(float SpotX, float SpotY);
	void Score(int32 Team, int32 Points, int32 PlayerIndex);
	void NextAfterScore();
	void EndQuarter();
	void AddFury(int32 Team, float Amount);
	void TickFuryAfterPlay();

	// Live play (FurySimPlay.cpp)
	void StepLive(float Dt, const FFurySeatInput* Inputs);
	void StepHuman(FFurySimPlayer& Player, int32 Index, const FFurySeatInput& Input, float Dt, FVector2D& OutWish, float& OutSpeed);
	void MovePlayers(float Dt, const FVector2D* Wish, const float* Speed);
	void Separate();
	void StepEngagements(float Dt);
	void StepBall(float Dt);
	void StepContacts(float Dt);
	void StepRules();
	void SetAct(FFurySimPlayer& Player, EFuryAct Act, uint8 Variant, float Length, float Key, bool bBusy);
	void ActKey(int32 Index);
	void StartStrike(int32 Index, EFuryAct Act, FVector2D Aim);
	void StartElbow(int32 Index, int32 Target);
	void ActEnd(int32 Index);
	void FinishCarrierDown(int32 Carrier, float SpotX, float SpotY, bool bOutOfBounds, int32 Tackler);
	void FinishLooseBallDown(float SpotX, float SpotY);
	void Knock(int32 Victim, int32 By, EFuryFall Fall, float DownSeconds, const FVector2D& Push, float Lift);
	void StartThrow(int32 Passer, int32 Target);
	void ReleaseThrow(int32 Passer);
	void GiveBall(int32 To);
	void ResolveCatch(const TArray<int32, TInlineAllocator<Fury::NumPlayers>>& InReach);
	void CompleteCatch(int32 Index);
	void FieldKick(int32 Index);
	bool Tackle(int32 Tackler, int32 Carrier, float Strength, bool bDive);
	void Fumble(int32 Carrier, const FVector2D& Push);
	void Engage(int32 Blocker, int32 Defender, float ShedSeconds);
	void Disengage(int32 Index);
	void SwitchSeat(int32 SeatIndex, int32 NewPlayer);
	void ControlFollowsBall(int32 NewHolder);
	void StartKick(int32 Kicker);
	void StrikeKick(int32 Kicker);
	void DownBall(float SpotX, float SpotY, const TCHAR* Title, const FString& Detail, int32 Team);
	float MaxSpeed(const FFurySimPlayer& Player, bool bTurbo) const;
	int32 NearestOpponent(int32 Index, float MaxDist, bool bUprightOnly = true) const;
	int32 ClosestToBall(int32 Team, bool bExcludeHumans, int32 Exclude = INDEX_NONE) const;

	// Brains (FurySimAI.cpp)
	void ThinkPlayer(FFurySimPlayer& Player, int32 Index, float Dt, FVector2D& OutWish, float& OutSpeed);
	void ThinkPasser(FFurySimPlayer& Player, int32 Index, float Dt, FVector2D& OutWish, float& OutSpeed);
	void ThinkCarrier(FFurySimPlayer& Player, int32 Index, float Dt, FVector2D& OutWish, float& OutSpeed);
	void ThinkDefender(FFurySimPlayer& Player, int32 Index, float Dt, FVector2D& OutWish, float& OutSpeed);
	void ThinkBlocker(FFurySimPlayer& Player, int32 Index, float Dt, FVector2D& OutWish, float& OutSpeed);
	void ThinkReceiver(FFurySimPlayer& Player, int32 Index, float Dt, FVector2D& OutWish, float& OutSpeed);
	void ThinkAfterWhistle(FFurySimPlayer& Player, int32 Index, float Dt, FVector2D& OutWish, float& OutSpeed);
	float Openness(int32 Receiver, FVector2D& OutCatchPoint, float& OutTime) const;
	int32 PickBlockTarget(int32 Blocker, const FVector2D& Protect) const;
	FVector2D PursuitPoint(const FFurySimPlayer& Chaser, const FFurySimPlayer& Runner) const;
	FVector2D DelayedPos(int32 Index, float Seconds) const;
	void PairBlockers();

	// Helpers
	FVector2D ToWorld(const FVector2D& PlaySpaceYards) const;
	FVector2D ClampToField(const FVector2D& Point, float Margin = 60.f) const;
	float Rand() { return Random.FRand(); }
	float RandRange(float A, float B) { return Random.FRandRange(A, B); }
	bool Chance(float Probability) { return Random.FRand() < Probability; }
	int32 Global(int32 Team, int32 Slot) const { return Team * Fury::TeamSize + Slot; }

	FRandomStream Random;
	FFuryOffPlay CurrentOff;
	FFuryDefPlay CurrentDef;
	bool bHaveOffPlay = false, bHaveDefPlay = false;
	float KickFromYard = 35.f;
	bool FuryAtSnap[2] = {};
	float SnapDelay = 0.f;
	bool bBallCrossedLine = false;     // run or completed pass: everyone converts to pursuit / lead blocking
	bool bPassThrown = false;
	bool bChangeOfPossession = false;  // interception or fumble recovery during this play
	bool bKickTouched = false;
	bool bKickPossessed = false;       // somebody has had hold of this kick
	bool bReturnEnteredField = false;
	bool bFirstDownMade = false;
	int32 PassSeat = INDEX_NONE;       // human who threw the current pass
	int32 TeamDrives[2] = { 0, 0 };    // possessions so far, per team: rotates who calls plays and who plays quarterback
	bool bClockExpired = false;
	bool bTwoMinuteCalled = false;
	int32 OpeningKicker = 0;
	float StartLosX = 0.f;             // line of scrimmage when the play began
	float ReturnStartX = 0.f;
	float HutTimer = 0.f;
	float DeadSpotX = 0.f, DeadSpotY = 0.f;
	int32 PendingScoreTeam = INDEX_NONE;

	// Position history for coverage reaction lag: 30 samples per second.
	static constexpr int32 TrailLength = 24;
	FVector2D Trail[Fury::NumPlayers][TrailLength];
	int32 TrailHead = 0;
	float TrailTimer = 0.f;
};
