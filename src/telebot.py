from telegram import Update, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler, MessageHandler, filters, ContextTypes

import json
import io
import sys

from services import (
    generate_xray_config,
    generate_docker_compose,
    run_docker_compose,
    stop_docker_compose,
    remove_tmpdir,
    clean_all,
    refurbish_xray_inbound_intance,
    request_config_for_xray_inbound_instance,
    request_instance_protocol,
    request_instance_tag,
    list_xray_inbound_instances,
    remove_content_of_tmpdir
)

def main(bot_token:str, users_whitelist:list, config, tmpdir):
    
    async def help_command_handler(update:Update, context:ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is not None and update.message.chat_id in users_whitelist:
            
            help_answer = (
                "/help - show this message\n",
                "/restart - purge all configuration files and restart xray-cad\n",
                "/shutdown - turn off xray-cAD"
                "/lc - request list of all currently running inbound instances\n",
                "/gc - request configuration file for specific inbound instance\n",
                "/rc - refurbish (purge) specific inbound instance configuration",
            )
            
            await update.message.reply_text("".join(help_answer))

    async def restart_command_handler(update:Update, context:ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is not None and update.message.chat_id in users_whitelist:
            
            await update.message.reply_text("Regenerating xray-core config and docker compose... Restarting docker compose...")

            # some other functions except that EXCACTLY tmpdir (with it's unique name) exists - so it's can't be deleted.
            remove_content_of_tmpdir(tmpdir=tmpdir)

            generate_xray_config(config=config, tmpdir=tmpdir)
            generate_docker_compose(config=config, tmpdir=tmpdir)

            stop_docker_compose(tmpdir)
            run_docker_compose(tmpdir)

            await update.message.reply_text("System was successfully restarted. All your configuration files are gone now. Feel free to request new ones from me.")
    
    async def shutdown_command_handler(update:Update, context:ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is not None and update.message.chat_id in users_whitelist:

            stop_docker_compose(tmpdir)
            remove_tmpdir(tmpdir)

            await update.message.reply_text("System is about to shutdown... Goodbye!")

            sys.exit(0)

    async def lc_command_handler(update:Update, context:ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is not None and update.message.chat_id in users_whitelist:

            xray_inbound_intances = list_xray_inbound_instances(config=config, tmpdir=tmpdir)
            inbound_instances_str = ""

            for instance_num in xray_inbound_intances:
                tag = request_instance_tag(config=config, tmpdir=tmpdir, instance_num=instance_num)
                inbound_instances_str = inbound_instances_str + f"{tag}\n"

            await update.message.reply_text(inbound_instances_str)

    async def gc_command_handler(update:Update, context:ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is not None and update.message.chat_id in users_whitelist:

            xray_inbound_intances = list_xray_inbound_instances(config=config, tmpdir=tmpdir)

            keyboard = [
                [
                    InlineKeyboardButton(text=tag, callback_data=f"getconfigforinboundnum:{num}")
                    for num, tag in xray_inbound_intances.items()
                ]
            ]

            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(text="Which instance do you want the configuration file for?", reply_markup=reply_markup)

    async def rc_command_handler(update:Update, context:ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is not None and update.message.chat_id in users_whitelist:
            
            xray_inbound_intances = list_xray_inbound_instances(config=config, tmpdir=tmpdir)

            keyboard = [
                [
                    InlineKeyboardButton(text=tag, callback_data=f"refurbishinboundnum:{num}")
                    for num, tag in xray_inbound_intances.items()
                ]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(text="Which instance you want to refurbish?", reply_markup=reply_markup)

    async def gc_buttons_callback_handler(update:Update, context:ContextTypes.DEFAULT_TYPE) -> None:
        
        query = update.callback_query
        if query is not None and query.data is not None and query.message is not None:

            await query.answer()

            instance_num = int(query.data.split(":")[1])
            
            instance_config = request_config_for_xray_inbound_instance(config=config, tmpdir=tmpdir, instance_num=instance_num)
            
            if instance_config is not None:

                if request_instance_protocol(config=config, tmpdir=tmpdir, instance_num=instance_num) == "shadowsocks":

                    instance_config_string = "\n".join(f"{k}: {v}" for k, v in instance_config.items())
                
                    instance_config_json = io.BytesIO((json.dumps(instance_config_string, indent=4, ensure_ascii=False) + "\n").encode("utf-8"))
                    instance_config_json.seek(0)

                    await query.edit_message_text(instance_config_string)

                    await context.bot.send_document(
                        chat_id=query.message.chat.id,
                        document=instance_config_json,
                        filename="config.json"
                    )
                else:
                    await query.edit_message_text("Cannot get config for this type of instances. Sorry.")

    async def rc_buttons_callback_handler(update:Update, context:ContextTypes.DEFAULT_TYPE) -> None:
        
        query = update.callback_query
        if query is not None and query.data is not None:
            
            await query.answer()

            instance_num = int(query.data.split(":")[1])
            #print(f"instance_num: {instance_num} -- will be refurbish!")
            
            refurbish_xray_inbound_intance(config=config, tmpdir=tmpdir, instance_num=instance_num)
            await query.edit_message_text("The selected instance has been refurbished. If you need a new configuration file for it, feel free to request it from me.")

    #print(users_whitelist, bot_token)

    application = Application.builder().token(bot_token).build()
    
    application.add_handler(CommandHandler("help", help_command_handler))
    application.add_handler(CommandHandler("restart", restart_command_handler))
    application.add_handler(CommandHandler("shutdown", shutdown_command_handler))
    application.add_handler(CommandHandler("lc", lc_command_handler))
    application.add_handler(CommandHandler("gc", gc_command_handler))
    application.add_handler(CommandHandler("rb", rc_command_handler))
    
    application.add_handler(CallbackQueryHandler(gc_buttons_callback_handler, pattern="^getconfigforinboundnum:\\d+$"))
    application.add_handler(CallbackQueryHandler(rc_buttons_callback_handler, pattern="^refurbishinboundnum:\\d+$"))
    

    application.run_polling(allowed_updates=Update.ALL_TYPES)