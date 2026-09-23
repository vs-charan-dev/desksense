"""End-of-Day Summary & Daily Workspace Wellness Score Engine for DeskSense (Phase 5).
Computes:
1. Daily Score (0-100) using balanced weights:
   - Focus: 35%
   - Posture: 25%
   - Breaks: 15%
   - Phone: 15%
   - Consistency: 10%
   Safely handles missing or zero data without division-by-zero errors.
2. Actionable, non-medical behavioral insights and factual summaries.
   Mandatory non-medical wording for posture (no medical claims/diagnoses).
   Mandatory "estimated phone usage" wording.
3. Daily summary gating: appears only at configured time when enabled, at most once per day.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import datetime


@dataclass
class ScoreWeights:
    focus: float = 0.35
    posture: float = 0.25
    breaks: float = 0.15
    phone: float = 0.15
    consistency: float = 0.10


class DailySummaryEngine:
    """Calculates wellness scores, generates behavioral insights, and manages summary triggers."""

    def __init__(self, weights: Optional[ScoreWeights] = None):
        self.weights = weights or ScoreWeights()
        self.last_summary_date: Optional[str] = None

    def calculate_daily_score(
        self,
        focus_seconds: float,
        desk_seconds: float,
        posture_score: float,  # 0 to 100
        break_count: int,
        phone_seconds: float,
        target_focus_hours: float = 4.0,
        expected_breaks_per_hour: float = 1.0,
    ) -> Dict[str, Any]:
        """
        Calculates 0-100 score safely without division by zero.
        - Focus component (35%): ratio of focus time to desk time or target (clamped to 100).
        - Posture component (25%): posture score (clamped to 0-100).
        - Break component (15%): break frequency relative to hours worked.
        - Phone component (15%): lower phone usage = higher score.
        - Consistency component (10%): balance between active work and desk time.
        """
        desk_hours = max(0.0, desk_seconds / 3600.0)
        focus_hours = max(0.0, focus_seconds / 3600.0)
        phone_hours = max(0.0, phone_seconds / 3600.0)

        # 1. Focus Score (0 - 100)
        if desk_seconds > 0:
            focus_ratio = min(1.0, focus_seconds / max(1.0, desk_seconds))
            focus_subscore = focus_ratio * 100.0
        else:
            focus_subscore = 100.0 if focus_seconds >= (target_focus_hours * 3600.0) else 50.0

        # 2. Posture Score (0 - 100)
        posture_subscore = max(0.0, min(100.0, posture_score))

        # 3. Breaks Score (0 - 100)
        # Expected roughly 1 break every 1-2 hours worked
        target_breaks = max(1.0, desk_hours * expected_breaks_per_hour)
        if desk_hours > 0.5:
            break_subscore = min(100.0, (break_count / target_breaks) * 100.0)
        else:
            break_subscore = 100.0  # short or unmonitored day

        # 4. Phone Score (0 - 100)
        # 0 phone usage = 100 score; > 1 hour phone usage reduces score progressively
        if desk_seconds > 0:
            phone_ratio = phone_seconds / max(1.0, desk_seconds)
            phone_subscore = max(0.0, 100.0 - (phone_ratio * 200.0))
        else:
            phone_subscore = max(0.0, 100.0 - (phone_hours * 25.0))

        # 5. Consistency Score (0 - 100)
        if desk_hours > 0:
            consistency_subscore = min(100.0, (focus_hours / desk_hours) * 100.0)
        else:
            consistency_subscore = 80.0

        # Weighted calculation
        total_score = (
            (focus_subscore * self.weights.focus) +
            (posture_subscore * self.weights.posture) +
            (break_subscore * self.weights.breaks) +
            (phone_subscore * self.weights.phone) +
            (consistency_subscore * self.weights.consistency)
        )

        clamped_score = int(round(max(0.0, min(100.0, total_score))))

        return {
            "daily_wellness_score": clamped_score,
            "components": {
                "focus": round(focus_subscore, 1),
                "posture": round(posture_subscore, 1),
                "breaks": round(break_subscore, 1),
                "phone": round(phone_subscore, 1),
                "consistency": round(consistency_subscore, 1),
            },
            "weights": {
                "focus": self.weights.focus,
                "posture": self.weights.posture,
                "breaks": self.weights.breaks,
                "phone": self.weights.phone,
                "consistency": self.weights.consistency,
            }
        }

    def generate_actionable_insights(
        self,
        focus_seconds: float,
        desk_seconds: float,
        posture_score: float,
        break_count: int,
        phone_seconds: float,
        longest_focus_seconds: float = 0.0,
    ) -> List[str]:
        """
        Generates actionable, factual, and motivational insights.
        Adheres to non-medical language standards (no diagnoses or health claims).
        Properly designates phone data as 'estimated phone usage'.
        """
        insights: List[str] = []

        # Focus insight
        focus_mins = int(focus_seconds // 60)
        if focus_seconds >= 14400:  # 4h
            insights.append(f"Excellent momentum: you achieved {focus_mins // 60}h {focus_mins % 60}m of dedicated focus.")
        elif focus_seconds > 0:
            insights.append(f"Recorded {focus_mins} minutes of focused work today. Tomorrow, try starting your most demanding task first.")
        else:
            insights.append("No dedicated focus sessions recorded yet. Try starting a 25-minute Pomodoro session tomorrow.")

        # Longest session insight
        if longest_focus_seconds >= 3600:
            l_hrs = int(longest_focus_seconds // 3600)
            l_mins = int((longest_focus_seconds % 3600) // 60)
            insights.append(f"Your longest deep-focus block was {l_hrs}h {l_mins}m.")

        # Posture insight (Non-medical wording: ergonomic awareness, comfort, alignment)
        if posture_score >= 80:
            insights.append(f"Great ergonomic alignment today ({posture_score:.0f}% upright comfort).")
        elif posture_score > 0:
            insights.append(f"Your upright posture score was {posture_score:.0f}%. Adjusting your chair height or monitor position may improve workday comfort.")

        # Break insight
        desk_hours = desk_seconds / 3600.0
        if desk_hours >= 3.0 and break_count < 2:
            insights.append("You had extended continuous desk time today. A brief 2-minute stretch every hour can refresh attention.")
        elif break_count >= 3:
            insights.append(f"Good pacing: you took {break_count} wellness breaks to reset and stretch.")

        # Phone insight (Mandatory 'estimated' labeling)
        phone_mins = int(round(phone_seconds / 60))
        if phone_seconds > 1800:
            insights.append(f"Estimated phone usage was {phone_mins} minutes today. Placing your phone out of arm's reach during deep-focus blocks can minimize interruptions.")
        elif phone_seconds > 0:
            insights.append(f"Minimal phone distraction: estimated phone usage was only {phone_mins} minutes.")
        else:
            insights.append("Zero phone distractions detected during your desk time.")

        return insights

    def generate_daily_summary(
        self,
        date_str: str,
        focus_seconds: float,
        desk_seconds: float,
        away_seconds: float,
        phone_seconds: float,
        posture_score: float,
        break_count: int,
        longest_focus_seconds: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Builds complete end-of-day summary payload with 0 double-counted durations.
        """
        score_data = self.calculate_daily_score(
            focus_seconds=focus_seconds,
            desk_seconds=desk_seconds,
            posture_score=posture_score,
            break_count=break_count,
            phone_seconds=phone_seconds,
        )

        insights = self.generate_actionable_insights(
            focus_seconds=focus_seconds,
            desk_seconds=desk_seconds,
            posture_score=posture_score,
            break_count=break_count,
            phone_seconds=phone_seconds,
            longest_focus_seconds=longest_focus_seconds,
        )

        return {
            "date": date_str,
            "metrics": {
                "focus_seconds": int(round(focus_seconds)),
                "desk_seconds": int(round(desk_seconds)),
                "away_seconds": int(round(away_seconds)),
                "estimated_phone_seconds": int(round(phone_seconds)),
                "posture_score": round(posture_score, 1),
                "break_count": break_count,
                "longest_focus_seconds": int(round(longest_focus_seconds)),
            },
            "score": score_data,
            "insights": insights,
            "wording_disclaimer": "Phone usage metrics are estimates. Posture scores reflect visual positioning for ergonomic comfort and do not constitute medical diagnosis.",
        }

    def should_trigger_summary(
        self,
        current_time: datetime.datetime,
        configured_time_str: str = "17:30",
        enabled: bool = True,
    ) -> bool:
        """
        Evaluates whether end-of-day summary dialog should trigger.
        - Enabled check.
        - Triggers once per calendar day at or after configured time.
        """
        if not enabled:
            return False

        today_date = current_time.strftime("%Y-%m-%d")
        if self.last_summary_date == today_date:
            return False

        try:
            target_hour, target_min = map(int, configured_time_str.split(":"))
        except Exception:
            target_hour, target_min = 17, 30

        scheduled_time = current_time.replace(hour=target_hour, minute=target_min, second=0, microsecond=0)
        if current_time >= scheduled_time:
            self.last_summary_date = today_date
            return True

        return False
