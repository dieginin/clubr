import uuid

import pyrebase
from flet import Page
from flet.security import decrypt, encrypt

from services import BrawlAPI
from utils import FIREBASE_CONFIG

SECRET_KEY = "sample"


class Fyrebase:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.firebase = pyrebase.initialize_app(FIREBASE_CONFIG)
        self.auth = self.firebase.auth()
        self.db = self.firebase.database()
        self.ba = BrawlAPI()

        self.idToken = None
        self.uuid = None
        self.club_tag = None

    @property
    def clubs(self):
        try:
            return {
                club.key(): club.val()["code"] for club in self.db.child("clubs").get()
            }
        except:
            return {}

    @property
    def users(self):
        try:
            return [
                user
                for club in self.db.child("clubs").get()
                for user in club.val()["users"].keys()
            ]
        except:
            return []

    def _get_members(self, club):
        try:
            return [
                m for m in self.db.child("clubs").child(club).child("members").get()
            ]
        except:
            return []

    def _save_token(self, token, uuid):
        self.page.client_storage.set("firebase_token", encrypt(token, SECRET_KEY))
        self.page.client_storage.set("firebase_id", uuid)
        self.idToken = token
        self.uuid = uuid

    def _erase_token(self):
        self.page.client_storage.remove("firebase_token")
        self.page.client_storage.remove("firebase_id")

    def active_sesion(self) -> bool:
        encrypted_token = self.page.client_storage.get("firebase_token")
        uuid = self.page.client_storage.get("firebase_id")
        if encrypted_token:
            decrypted_token = decrypt(encrypted_token, SECRET_KEY)
            self.idToken = decrypted_token
            self.uuid = uuid
            try:
                self.auth.get_account_info(self.idToken)
                return True
            except:
                return False
        return False

    def _register_user(self, club, username, email, password):
        if username in self.users:
            return "Usuario existente"

        try:
            self.auth.create_user_with_email_and_password(email, password)
            self._sign_in(email, password)
        except:
            return "Correo existente"

        self.db.child("clubs").child(club).child("users").child(username).set(
            {"email": email}
        )
        return True

    def register_club(self, club, username, email, password):
        if club in self.clubs:
            return "Club existente, pide el código"
        try:
            club_data = self.ba.club(club)
        except:
            return "Club tag incorrecto"

        code = str(uuid.uuid4()).upper()[:6]
        register = self._register_user(club, username, email, password)
        if register == True:
            self.db.child("clubs").child(club).update(
                {"code": code, "name": club_data.name, "trophies": club_data.trophies}
            )
            self.page.client_storage.set("club_tag", club)
            self.update_club()
            return True
        return register

    def update_club(self):
        club = self.page.client_storage.get("club_tag")
        members = self._get_members(club)

        club_data = self.ba.club(club)
        for m in members:
            if m.key() not in [m.tag for m in club_data.members]:
                self.db.child("clubs").child(club).child("old_members").child(
                    m.tag
                ).set(self.db.child("clubs").child(club).child("members").child(m.tag))
                self.db.child("clubs").child(club).child("members").child(
                    m.tag
                ).remove()

        for m in club_data.members:
            if m.tag not in members:
                self.db.child("clubs").child(club).child("members").child(m.tag).set(
                    {
                        "name": m.name,
                        "trophies": m.trophies,
                        "role": m.role,
                        "phone": None,
                        "strikes": 0,
                    }
                )
            else:
                self.db.child("clubs").child(club).child(m.tag).update(
                    {
                        "name": m.name,
                        "trophies": m.trophies,
                        "role": m.role,
                    }
                )

    def _get_club(self, code):
        for clave, val in self.clubs.items():
            if val == code:
                return clave
        return None

    def add_member(self, code, username, email, password):
        club = self._get_club(code)
        if not club:
            return "Código in-existente"

        return self._register_user(club, username, email, password)

    def _sign_in(self, email, password):
        try:
            user = self.auth.sign_in_with_email_and_password(email, password)
            if user:
                token = user["idToken"]
                uuid = user["localId"]
                self._save_token(token, uuid)
                return True
            return "Revisa credenciales"
        except:
            return "Contraseña incorrecta"

    def sign_out(self):
        self._erase_token()

    def _get_email(self, username):
        try:
            for club in self.db.child("clubs").get():
                for user, data in club.val()["users"].items():
                    if user == username:
                        return data.get("email")
        except:
            return None

    def log_in(self, username, password):
        email = self._get_email(username)
        if not email:
            return "No se encontró el usuario"

        try:
            return self._sign_in(email, password)
        except:
            return "Error en inicio"

    def send_reset_email(self, email):
        self.auth.send_password_reset_email(email)
