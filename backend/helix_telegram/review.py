"""Telegram bot review queue for human-in-the-loop moderation."""

import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

@dataclass
class ReviewItem:
    """Item pending human review."""
    id: str
    alert_data: Dict[str, Any]
    created_at: float
    score: float  # Higher score = more likely to need review
    reviewed: bool = False
    approved: Optional[bool] = None
    reviewed_at: Optional[float] = None

class ReviewQueue:
    """In-memory review queue for alerts that might need human review."""
    
    def __init__(self, auto_approve_timeout_minutes: int = 5):
        """
        Initialize review queue.
        
        Args:
            auto_approve_timeout_minutes: Auto-approve after this many minutes
        """
        self.auto_approve_timeout = auto_approve_timeout_minutes * 60  # Convert to seconds
        self.queue: Dict[str, ReviewItem] = {}  # review_id -> ReviewItem
        self._next_id = 1
    
    def add_for_review(self, alert_data: Dict[str, Any]) -> str:
        """
        Add an alert to the review queue.
        
        Args:
            alert_data: Alert data to review
            
        Returns:
            str: Review ID
        """
        # Calculate review score (higher = more likely to need review)
        score = self._calculate_review_score(alert_data)
        
        # Only add to queue if score is high enough
        if score < 0.3:  # Threshold for requiring review
            return "auto_approved"
        
        review_id = f"review_{self._next_id}"
        self._next_id += 1
        
        item = ReviewItem(
            id=review_id,
            alert_data=alert_data,
            created_at=time.time(),
            score=score
        )
        
        self.queue[review_id] = item
        logger.info(f"Added alert to review queue: {review_id} (score: {score:.2f})")
        
        return review_id
    
    def approve(self, review_id: str) -> bool:
        """
        Approve a review item.
        
        Args:
            review_id: Review ID to approve
            
        Returns:
            bool: True if successful
        """
        item = self.queue.get(review_id)
        if not item or item.reviewed:
            return False
            
        item.reviewed = True
        item.approved = True
        item.reviewed_at = time.time()
        logger.info(f"Approved review item: {review_id}")
        return True
    
    def reject(self, review_id: str) -> bool:
        """
        Reject a review item.
        
        Args:
            review_id: Review ID to reject
            
        Returns:
            bool: True if successful
        """
        item = self.queue.get(review_id)
        if not item or item.reviewed:
            return False
            
        item.reviewed = True
        item.approved = False
        item.reviewed_at = time.time()
        logger.info(f"Rejected review item: {review_id}")
        return True
    
    def get_pending(self) -> List[ReviewItem]:
        """
        Get all pending (unreviewed) items.
        
        Returns:
            List[ReviewItem]: List of pending review items
        """
        now = time.time()
        pending = []
        
        for item in self.queue.values():
            if item.reviewed:
                continue
                
            # Check if auto-approve timeout has passed
            if now - item.created_at > self.auto_approve_timeout:
                item.reviewed = True
                item.approved = True
                item.reviewed_at = now
                logger.info(f"Auto-approved review item {item.id} due to timeout")
                continue
                
            pending.append(item)
            
        # Sort by score (highest first) then by creation time (oldest first)
        pending.sort(key=lambda x: (-x.score, x.created_at))
        return pending
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get queue statistics.
        
        Returns:
            Dict[str, int]: Statistics
        """
        total = len(self.queue)
        pending = len([item for item in self.queue.values() if not item.reviewed])
        approved = len([item for item in self.queue.values() if item.reviewed and item.approved])
        rejected = len([item for item in self.queue.values() if item.reviewed and item.approved is False])
        
        return {
            "total": total,
            "pending": pending,
            "approved": approved,
            "rejected": rejected
        }
    
    def _calculate_review_score(self, alert_data: Dict[str, Any]) -> float:
        """
        Calculate review score for an alert (0.0 - 1.0).
        Higher scores are more likely to need review.
        
        Args:
            alert_data: Alert data
            
        Returns:
            float: Review score
        """
        score = 0.0
        
        # Severity affects score
        severity = alert_data.get("severity", "").lower()
        if severity == "critical":
            score += 0.8
        elif severity == "high":
            score += 0.6
        elif severity == "medium":
            score += 0.3
        elif severity == "low":
            score += 0.1
            
        # Alert type affects score
        alert_type = alert_data.get("type", "").lower()
        if "depeg" in alert_type or "anomaly" in alert_type:
            score += 0.4
        elif "supply" in alert_type:
            score += 0.3
        elif "price" in alert_type:
            score += 0.2
            
        # Confidence affects score
        confidence = alert_data.get("confidence", 0.0)
        if confidence < 0.5:
            score += 0.3
        elif confidence < 0.8:
            score += 0.1
            
        # Cap score at 1.0
        return min(1.0, score)

# Global review queue instance
review_queue = ReviewQueue(auto_approve_timeout_minutes=5)