PC内に以前 `git clone` したプロジェクトが存在する場合、`git pull` コマンドを使用すれば、GitHub上の最新のソースコードを取得できます。

## 1. 基本的な操作

まず、既存のプロジェクトフォルダに移動します。

```
cd etstartpg
```

現在のブランチを確認します。

```
git branch
```

`main` ブランチの最新ソースを取得する場合は、次のコマンドを実行します。

```
git switch main
git pull origin main
```

これで、GitHub上の最新の `main` ブランチがローカルPCに反映されます。

## 2. ローカルで変更したファイルがある場合

`git pull` の前に、次のコマンドで変更状態を確認してください。

```
git status
```

ローカルの変更を残したまま更新したい場合は、次のようにします。

```
git stash
git pull origin main
git stash pop
```

ただし、変更内容によっては競合（コンフリクト）が発生することがあります。

## 3. GitHubの内容で完全に上書きしたい場合

ローカルの変更をすべて破棄し、GitHubと同じ状態に戻したい場合は、次のコマンドを使用します。

```
git fetch origin
git reset --hard origin/main
```

注意： この操作では、追跡対象ファイルの未コミット変更や、GitHubに存在しないローカルコミットが失われる可能性があります。未追跡ファイルは削除されません。

## 4. コマンドの使い分け

| コマンド                           | 用途                         |
| ------------------------------ | -------------------------- |
| `git clone URL`                | 初めてプロジェクトを取得する             |
| `git fetch origin`             | GitHubの最新情報だけ取得する          |
| `git pull origin main`         | GitHubの最新内容を現在のブランチに統合する   |
| `git reset --hard origin/main` | ローカルの追跡対象ファイルをGitHubの状態に戻す |

今回のように、以前cloneしたプロジェクトを最新状態に更新するだけなら、基本的には以下の2行で十分です。

```
git switch main
git pull origin main
```

なお、GitHubで `develop` ブランチを更新している場合は、`main` を `develop` に置き換えてください。