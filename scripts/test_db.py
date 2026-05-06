from db import dao

DB = 'db/games.sqlite'

if __name__ == '__main__':
    conn = dao.init_db(DB)
    game_id = dao.insert_game(conn, '2026-05-05')
    sid = dao.insert_screenshot(conn, game_id, 1, 'https://example.com/1.png', 'Test Location', 12.34, 56.78, None, 'desc')
    print('Inserted game', game_id, 'inserted screenshot', sid)
    rows = conn.execute('SELECT * FROM screenshots').fetchall()
    for r in rows:
        print(dict(r))
    conn.close()
