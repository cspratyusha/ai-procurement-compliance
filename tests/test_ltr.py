import sys
import numpy as np
import lightgbm as lgb
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data_loader import load_corpus
from ltr.features import build_features, fallback_score, FEATURE_NAMES, compute_recency_score
from ltr.train import (
    build_training_data,
    split_training_data,
    train_ltr_model,
    save_model,
    load_model,
    save_training_report,
    ltr_predict,
)


def test_ltr_pipeline():
    print("=" * 70)
    print("TESTING LEARNING-TO-RANK (LTR) LAYER")
    print("=" * 70)

    # 1. Test feature vector length and order
    print("\n--- [Test 1] Feature Vector Length & Alignment ---")
    corpus = load_corpus()
    sample_std = corpus[0]
    
    fv = build_features(
        query="PVC single core electrical conduit wiring",
        candidate_id=sample_std.id,
        standard=sample_std,
        dense_score=0.88,
        bm25_score_normalized=0.92,
        cross_encoder_score=5.4,
        historical_acceptance_rate=0.75,
        current_year=2026
    )

    assert len(fv) == len(FEATURE_NAMES), f"Expected {len(FEATURE_NAMES)} features, got {len(fv)}"
    assert fv[0] == 0.88, "Feature 0 (dense_score) mismatch"
    assert fv[1] == 0.92, "Feature 1 (bm25_score_normalized) mismatch"
    assert fv[2] == 5.4, "Feature 2 (cross_encoder_score) mismatch"
    assert 0.0 <= fv[3] <= 1.0, "Feature 3 (recency_score) out of range"
    assert 0.0 <= fv[4] <= 1.0, "Feature 4 (category_match) out of range"
    assert 0.0 <= fv[5] <= 1.0, "Feature 5 (keyword_overlap) out of range"
    assert fv[6] == 0.75, "Feature 6 (historical_acceptance_rate) mismatch"
    print(f"  [PASS] Features successfully aligned with FEATURE_NAMES: {FEATURE_NAMES}")

    # 2. Test fallback scoring without trained model
    print("\n--- [Test 2] Heuristic Fallback Score ---")
    score = fallback_score(fv)
    expected_fallback = 0.3 * 0.88 + 0.2 * 0.92 + 0.5 * 5.4
    assert abs(score - expected_fallback) < 1e-6, f"Expected {expected_fallback}, got {score}"
    print(f"  [PASS] Fallback score computed correctly ({score:.4f}) without requiring a model.")

    # 3. Test training, early stopping, and report generation
    print("\n--- [Test 3] Training Loop, Visibility & Report Verification ---")
    X, y, groups, meta = build_training_data()
    X_train, y_train, g_train, X_val, y_val, g_val, _, _ = split_training_data(
        X, y, groups, meta, val_ratio=0.2, seed=42
    )

    booster, report = train_ltr_model(
        X_train, y_train, g_train,
        X_val, y_val, g_val,
        n_estimators=50,
        learning_rate=0.08
    )

    val_hist = report["val_ndcg5_history"]
    total_rounds = report["total_rounds_trained"]
    best_iter = report["best_iteration"]

    assert len(val_hist) == total_rounds, f"Expected val history length {total_rounds}, got {len(val_hist)}"
    assert 1 <= best_iter <= total_rounds, f"Best iteration {best_iter} outside [1, {total_rounds}]"
    assert report["best_val_ndcg5"] > 0.0, "Best val NDCG@5 should be positive"
    print(f"  [PASS] Training report verified: Total rounds={total_rounds}, Best iteration=#{best_iter}, Best Val NDCG@5={report['best_val_ndcg5']:.4f}")

    # 4. Test model truncation on save
    print("\n--- [Test 4] Model Truncation & Roundtrip Verification ---")
    test_model_path = Path("scratch/test_ltr_model.txt")
    test_model_path.parent.mkdir(parents=True, exist_ok=True)

    save_model(booster, path=test_model_path, num_iteration=best_iter)
    loaded_booster = load_model(path=test_model_path, force_reload=True)

    # In LightGBM, when a model is saved with num_iteration=N, loaded_booster.num_trees() equals N
    assert loaded_booster is not None, "Failed to reload saved booster"
    assert loaded_booster.num_trees() == best_iter, f"Expected {best_iter} trees in saved model, got {loaded_booster.num_trees()}"

    # Verify predictions match
    pred_orig = booster.predict(X_val[:5], num_iteration=best_iter)
    pred_loaded = loaded_booster.predict(X_val[:5])
    np.testing.assert_allclose(pred_orig, pred_loaded, rtol=1e-5, atol=1e-5)
    print(f"  [PASS] Model saved with exactly {loaded_booster.num_trees()} trees (matching best_iteration #{best_iter}) and predictions match perfectly.")

    print("\n" + "=" * 70)
    print("All Learning-to-Rank (LTR) tests passed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    test_ltr_pipeline()
