import os
import argparse
import pandas as pd

def split_df(df: pd.DataFrame, train: float, val: float, seed: int) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df = df.sample(frac=1, random_state=seed).reset_index(drop=True)  # shuffle
    n = len(df)
    n_train = int(n * train)
    n_val = int(n * val)
    train_df = df.iloc[:n_train]
    val_df = df.iloc[n_train:n_train + n_val]
    test_df = df.iloc[n_train + n_val:]
    return train_df, val_df, test_df

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to input CSV (raw dataset)")
    ap.add_argument("--outdir", required=True, help="Output directory for splits")
    ap.add_argument("--train", type=float, default=0.8)
    ap.add_argument("--val", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--stratify_col", default=None, help="Optional column to stratify on (classification labels)")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    df = pd.read_csv(args.input)

    if args.stratify_col and args.stratify_col in df.columns:
        # stratified split (simple group-wise split)
        parts = []
        for _, g in df.groupby(args.stratify_col):
            parts.append(split_df(g, args.train, args.val, args.seed))
        train_df = pd.concat([p[0] for p in parts]).sample(frac=1, random_state=args.seed)
        val_df   = pd.concat([p[1] for p in parts]).sample(frac=1, random_state=args.seed)
        test_df  = pd.concat([p[2] for p in parts]).sample(frac=1, random_state=args.seed)
    else:
        train_df, val_df, test_df = split_df(df, args.train, args.val, args.seed)

    train_df.to_csv(os.path.join(args.outdir, "train.csv"), index=False)
    val_df.to_csv(os.path.join(args.outdir, "val.csv"), index=False)
    test_df.to_csv(os.path.join(args.outdir, "test.csv"), index=False)

    print("Saved:",
          os.path.join(args.outdir, "train.csv"),
          os.path.join(args.outdir, "val.csv"),
          os.path.join(args.outdir, "test.csv"))

if __name__ == "__main__":
    main()