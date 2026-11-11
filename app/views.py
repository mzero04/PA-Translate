from flask import Blueprint, g, redirect, render_template, url_for

from .auth import admin_required, login_required

bp = Blueprint("views", __name__)


def render_error(code, message):
    return render_template("error.html", code=code, message=message), code


@bp.route("/")
@login_required
def translate():
    return render_template("translate.html", page="translate")


@bp.route("/kamus")
@login_required
def dictionary():
    return render_template("dictionary.html", page="dictionary")


@bp.route("/gabung")
@login_required
def combine():
    return render_template("combine.html", page="combine")


@bp.route("/riwayat")
@login_required
def history():
    return render_template("history.html", page="history")


@bp.route("/akun")
@login_required
def account():
    return render_template("account.html", page="account")


@bp.route("/pengguna")
@admin_required
def users():
    return render_template("users.html", page="users")
