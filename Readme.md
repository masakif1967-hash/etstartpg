# 仮想環境での起動方法
Pythonの仮想環境 `.venv` を使用して、`requirements.txt` に定義されたライブラリをインストールし、プログラムを実行するまでの手順を、Windows 11（PowerShell） と Linux Mint（Ubuntu系） に分けて説明します。

GitHubから `etstartpg` を取得した場合を例にします。

## 1. Windows 11（PowerShell）

### ① プロジェクトフォルダへ移動

```
cd C:\Users\fukada\Documents\developer\python\etstartpg
```

GitHubから新規取得する場合は、先に次を実行します。

```
git clone https://github.com/masakif1967-hash/etstartpg.git
cd etstartpg
```

### ② 仮想環境を作成

```
python -m venv .venv
```

プロジェクト内に `.venv` フォルダが作成されます。

### ③ 仮想環境を有効化

```
.\.venv\Scripts\Activate.ps1
```

成功すると、プロンプトの先頭に `(.venv)` が表示されます。

```
(.venv) PS C:\Users\fukada\Documents\developer\python\etstartpg>
```

PowerShellの実行ポリシーによって有効化できない場合は、次を実行してください。

```
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

これは現在のPowerShellセッションだけに適用されます。その後、再び `Activate.ps1` を実行します。

### ④ pipを更新

```
python -m pip install --upgrade pip
```

### ⑤ requirements.txtからライブラリをインストール

```
python -m pip install -r requirements.txt
```

これで必要なライブラリが `.venv` 内にインストールされます。

### ⑥ Pythonプログラムを実行

例えば、実行ファイルが `starting.py` なら、

```
python starting.py
```

### ⑦ 仮想環境を終了

```
deactivate
```

## 2. Linux Mint（Ubuntu系）

### ① Pythonの仮想環境関連パッケージをインストール

初回のみ実行します。

```
sudo apt update
sudo apt install python3 python3-venv python3-pip
```

### ② プロジェクトフォルダへ移動

```
cd ~/developer/python/etstartpg
```

GitHubから新規取得する場合は、

```
git clone https://github.com/masakif1967-hash/etstartpg.git
cd etstartpg
```

### ③ 仮想環境を作成

```
python3 -m venv .venv
```

### ④ 仮想環境を有効化

```
source .venv/bin/activate
```

成功すると、

```
(.venv) user@LinuxMint:~/developer/python/etstartpg$
```

のようになります。

### ⑤ pipを更新

```
python -m pip install --upgrade pip
```

### ⑥ requirements.txtからライブラリをインストール

```
python -m pip install -r requirements.txt
```

Linux Mintでは、システムのPythonに直接 `pip install` すると `externally-managed-environment` エラーが発生する場合がありますが、仮想環境を有効化していれば通常は問題ありません。

### ⑦ Pythonプログラムを実行

```
python starting.py
```

### ⑧ 仮想環境を終了

```
deactivate
```

## 3. WindowsとLinuxのコマンド比較

| 操作      | Windows（PowerShell）                         | Linux（bash）                 |
| ------- | ------------------------------------------- | --------------------------- |
| 仮想環境作成  | `python -m venv .venv`                      | `python3 -m venv .venv`     |
| 仮想環境有効化 | `.\.venv\Scripts\Activate.ps1`              | `source .venv/bin/activate` |
| pip更新   | `python -m pip install -U pip`              | 同左                          |
| ライブラリ導入 | `python -m pip install -r requirements.txt` | 同左                          |
| プログラム実行 | `python starting.py`                        | 同左                          |
| 仮想環境終了  | `deactivate`                                | 同左                          |

## 4. 2回目以降の起動方法

一度 `.venv` を作成し、必要なライブラリをインストールしたら、次回以降は仮想環境の作成とライブラリの再インストールは不要です。

Windows

```
cd C:\Users\fukada\Documents\developer\python\etstartpg
.\.venv\Scripts\Activate.ps1
python starting.py
```

Linux Mint

```
cd ~/developer/python/etstartpg
source .venv/bin/activate
python starting.py
```

## 5. GitHubで管理する場合の注意点

`.venv` はWindowsとLinuxで内部構造が異なるため、GitHubには登録せず、それぞれのOSで作成するのが基本です。

`.gitignore` に次を記述します。

```
.venv/
__pycache__/
*.pyc
```

一方、`requirements.txt` はGitHubに登録してください。

ライブラリを追加したときは、仮想環境を有効化した状態で、

```
python -m pip freeze > requirements.txt
```

とすれば、現在インストールされているライブラリとバージョンを記録できます。

ただし、`pip freeze` は不要な依存パッケージも含めて出力するため、既存の `requirements.txt` を上書きする前に内容を確認することをおすすめします。

また、GitHubから最新版を `git pull` した後、`requirements.txt` が変更されていれば、再度インストールコマンドを実行してください。

## 6. 仮想環境が正しく使われているか確認する

仮想環境を有効化した状態で、次を実行します。

```
python -c "import sys; print(sys.executable)"
```

Windowsでは、

```
C:\Users\fukada\Documents\developer\python\etstartpg\.venv\Scripts\python.exe
```

Linuxでは、

```
/home/user/developer/python/etstartpg/.venv/bin/python
```

のように `.venv` 配下のPythonが表示されれば正常です。

補足： 仮想環境は必ずしも有効化する必要はありません。例えばWindowsなら `.\.venv\Scripts\python.exe starting.py`、Linuxなら `.venv/bin/python starting.py` と実行すれば、有効化せずに仮想環境内のPythonを使用できます。

ただし、普段の開発では `activate` を使用する方が便利です。