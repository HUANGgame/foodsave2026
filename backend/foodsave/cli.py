import argparse
import getpass
from pydantic import ValidationError
from .admin import AdminService
from .schemas import Credentials, NewPassword
from .ranking import RankingService


def main():
    parser = argparse.ArgumentParser(description='FoodSave dedicated database maintenance')
    parser.add_argument('command', choices=['create-user','expire','settle-week'])
    parser.add_argument('--email')
    parser.add_argument('--role', choices=['consumer','vendor','admin'], default='consumer')
    args = parser.parse_args()
    svc = AdminService()
    if args.command == 'settle-week':
        print(RankingService().settle_previous_week())
    elif args.command == 'expire':
        print('Expired reservations:', svc.expire_reservations())
    else:
        try:
            body = Credentials(email=args.email or input('Email: '), password=getpass.getpass('Password (15+ characters): '))
            NewPassword(password=body.password)
        except ValidationError:
            parser.error('Invalid email or password policy; values withheld')
        if getpass.getpass('Repeat password: ') != body.password:
            parser.error('Passwords do not match')
        result = svc.register(body.email, body.password, args.role)
        print('Created user id:', result['id'], 'role:', result['role'])


if __name__ == '__main__':
    main()
