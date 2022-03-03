import datetime
import time

import redis
from telegram import Update
from telegram.ext import (CallbackContext, CommandHandler, MessageHandler,
                          Updater)

try:
  from src.config import config
except:
  print("Please rename 'src/.config.py' file to 'src/config.py' and fill the variables with proper values.")
  exit()

try:
  r = redis.Redis(host=config['redis-server'], port=config['redis-port'],
                  db=config['redis-db-number'], charset="utf-8", decode_responses=True)
except Exception as e:
  print("Error while connecting to database, ", str(e))
  exit()

types = {
    'text': ['📝', 'Text', 'Texts', '文字发言'],
    'sticker': ['🧩', 'Sticker', 'Stickers', '贴纸发言'],
}

# 只记录30天发言
RECORD_PERIOD = 30


class Bot:
  me = None
  bot = None

  def start(self):
    updater = Updater(config["token"], use_context=True)
    updater.dispatcher.add_handler(
        CommandHandler('mystats', callback=self.stats_command))
    updater.dispatcher.add_handler(
        CommandHandler('clear', callback=self.clear_command))
    updater.dispatcher.add_handler(
        MessageHandler(None, callback=self.new_message))

    updater.dispatcher.add_error_handler(self.error_cb)
    self.me = updater.bot.get_me()
    self.bot = updater.bot
    print(self.me.username, 'started.')
    updater.start_polling()
    updater.idle()

  def error_cb(self, update: Update, context: CallbackContext):
    print("Error: ", context.error)

  def new_message(self, update: Update, context: CallbackContext):
    if not update.message or not update.message.from_user or not update.message.chat or update.message.chat.type not in ['supergroup', 'group']:
      return
    if update.message.from_user.id < 10000000:
      return
    name = 'chat:{}_user:{}'.format(
        update.message.chat.id, update.message.from_user.id)
    data = r.hgetall(name)
    if 'last_message' not in data:
      data['last_message'] = str(time.time())
    last_time = int(data['last_message'].split(".")[0])
    now_time = int(time.time())
    difference = int(now_time/86400) - int(last_time/86400)
    for i in types.keys():
      if hasattr(update.message, i) and getattr(update.message, i):
        if i in data and data[i] :
          count_arr = data[i].split(" ")
          if difference == 0 :
            count_arr[-1] = str(int(count_arr[-1])+1)
          elif difference > 0:
            for i in range(1,difference):
              count_arr.append("0")
            count_arr.append("1")
          while len(count_arr) > RECORD_PERIOD :
            del count_arr[0]
          data[i] = " ".join(count_arr)
          break
        else :
          data[i] = "1"
          break
    data['total'] = int(data['total']) + \
        1 if 'total' in data and data['total'] else 1
    data['last_message'] = now_time
    r.hmset(name, data)

  def stats_command(self, update: Update, context: CallbackContext):
    if not update.message or not update.message.from_user or not update.message.chat or update.message.chat.type not in ['supergroup', 'group']:
      return
    if update.message.from_user.id < 1000000:
      return
    if update.message.reply_to_message:
      if not self.is_admin(update.message.chat.id, update.message.from_user.id):
        self.bot.send_message(
            chat_id=update.message.chat.id,
            text='Sorry, only admins can receive other members stats. To see your own stats, send /stats without replying.',
            reply_to_message_id=update.message.message_id)
        return
      user = update.message.reply_to_message.from_user
    else:
      user = update.message.from_user
    day = RECORD_PERIOD
    text_arr = update.message.text.split(" ")
    if len(text_arr) == 2:
      day = int(text_arr[1])
      if day <= 0:
        self.bot.send_message(
          chat_id=update.message.chat.id,
          text="指令错误",
          reply_to_message_id=update.message.message_id)
        return
    data = r.hgetall('chat:{}_user:{}'.format(update.message.chat.id, user.id))
    out = ''
    t = types.keys()
    count = 0
    for k, v in data.items():
      if k in t:
        count += 1
        sum = 0
        arr = v.split(" ")
        if day >= len(arr):
          for num in arr:
            sum += int(num)
        else :
          arr.reverse()
          for i in range (0,day):
            sum += int(arr[i])
        out += '{} {}: <b>{}</b>\n'.format(types[k][0], types[k][-1], sum)
    if not count:
      self.bot.send_message(
          chat_id=update.message.chat.id,
          text='{} has no stats yet.'.format(self.get_inlined_name(user)),
          parse_mode='html',
          reply_to_message_id=update.message.message_id)
      return
    out += '{}: <b>{}</b> <i>最后发言时间: {}</i>'.format('统计至今总发言数据', data['total'], datetime.datetime.fromtimestamp(
        float(data['last_message'])).strftime("%y/%d/%m %H:%M"))
    out = '{} {}天内发言数据:\n'.format(self.get_inlined_name(user),day)+out
    self.bot.send_message(
        chat_id=update.message.chat.id,
        text=out,
        parse_mode='html',
        reply_to_message_id=update.message.message_id)

  def clear_command(self, update: Update, context: CallbackContext):
    if not update.message or not update.message.from_user or not update.message.chat or update.message.chat.type not in ['supergroup', 'group']:
      return
    if not self.is_admin(update.message.chat.id, update.message.from_user.id):
      self.bot.send_message(
          chat_id=update.message.chat.id,
          text='Sorry, only admins can clear members stats.',
          reply_to_message_id=update.message.message_id)
      return
    if update.message.reply_to_message:
      user = update.message.reply_to_message.from_user
    else:
      user = update.message.from_user
    if r.delete('chat:{}_user:{}'.format(update.message.chat.id, user.id)):
      self.bot.send_message(
          chat_id=update.message.chat.id,
          text='{} stats cleared.'.format(self.get_inlined_name(user)),
          parse_mode='html',
          reply_to_message_id=update.message.message_id)

  def get_fullname(self, user):
    return user.first_name+(' '+user.last_name if user.last_name else '')

  def get_inlined_name(self, user):
    return '<a href="tg://user?id={}">{}</a>'.format(user.id, self.get_fullname(user))

  def is_admin(self, chat_id, user_id):
    chat_member = self.bot.get_chat_member(chat_id, user_id)
    if chat_member.status in ['creator', 'administrator']:
      return True
    return False
