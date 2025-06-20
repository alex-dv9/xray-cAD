from services import (
    generate_xray_config, 
    generate_docker_compose, 
    generate_tmpdir,
    remove_tmpdir,
    clean_all,
    parse_config,
    run_docker_compose,
    stop_docker_compose
)

from telebot import main as run_telegram_bot

def main():
    clean_all()

    config = parse_config()
    tmpdir = generate_tmpdir()

    if config is None:
        raise ValueError("[-] Config can't be empty!")
    else:
        telegram_bot_token = config["telegram_bot_token"]
        telegram_bot_users_whitelist = config["telegram_users_whitelist"] 

    generate_xray_config(config=config, tmpdir=tmpdir)    
    generate_docker_compose(config=config, tmpdir=tmpdir)

    run_docker_compose(tmpdir)

    run_telegram_bot(bot_token=telegram_bot_token, users_whitelist=telegram_bot_users_whitelist, config=config, tmpdir=tmpdir)

    stop_docker_compose(tmpdir)
    remove_tmpdir(tmpdir)

if __name__ == "__main__":
    main()