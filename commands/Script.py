import ast
import discord
from core import Context, Embeds
from traceback import format_exception


def insert_returns(body):
    # insert return stmt if the last expression is a expression statement
    if isinstance(body[-1], ast.Expr):
        body[-1] = ast.Return(body[-1].value)
        ast.fix_missing_locations(body[-1])

    # for if statements, we insert returns into the body and the orelse
    if isinstance(body[-1], ast.If):
        insert_returns(body[-1].body)
        insert_returns(body[-1].orelse)

    # for with blocks, again we insert returns into the body
    if isinstance(body[-1], ast.With):
        insert_returns(body[-1].body)


def get_traceback(error: Exception) -> str:
    traceback = ''.join(format_exception(None, error, error.__traceback__))
    if len(traceback) > 2000:
        traceback = traceback[:2000] + '...'
    return traceback


async def go(ctx: Context, code: str):
    """Evaluates input.

    Input is interpreted as newline seperated statements.
    If the last statement is an expression, that is the return value.

    Usable globals:
      - `bot`: the bot instance
      - `discord`: the discord module
      - `commands`: the discord.ext.commands module
      - `ctx`: the invokation context
      - `__import__`: the builtin `__import__` function

    Such that `>eval 1 + 1` gives `2` as the result.

    The following invokation will cause the bot to send the text '9'
    to the channel of invokation and return '3' as the result of evaluating

    >eval ```
    a = 1 + 2
    b = a * 2
    await ctx.reply(a + b)
    ```
    """
    fn_name = "_eval_expr"
    code = code.strip("` ")
    lines = code.splitlines()
    if lines[0] == 'py':
        lines = lines[1:]

    # add a layer of indentation
    cmd = "\n".join(f"    {i}" for i in lines)

    # wrap in async def body
    body = f"async def {fn_name}():\n{cmd}"

    parsed = ast.parse(body)
    body = parsed.body[0].body

    insert_returns(body)

    env = {
        'ctx': ctx,
        'bot': ctx.bot,
        'discord': discord,
        '__import__': __import__
    }
    try:
        exec(compile(parsed, filename="<ast>", mode="exec"), env)
        ret = await eval(f"{fn_name}()", env)
    except Exception as error:
        emb = Embeds.red(f"```prolog\n{get_traceback(error)}```")
    else:
        if not ret or isinstance(ret, discord.Message):
            result = '• No return'
        else:
            result = str(ret)[:4000]
        emb = Embeds.green(f"```prolog\n{result}```")
    await ctx.reply(embed=emb)