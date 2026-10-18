-- Additive MySQL 8 migration. Stop the live entry to roll back, retain audit/grants.
CREATE TABLE IF NOT EXISTS live_v2_session (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
 owner_id BIGINT UNSIGNED NOT NULL,
 title VARCHAR(80) NOT NULL,
 scheduled_at BIGINT NOT NULL,
 status VARCHAR(16) NOT NULL DEFAULT 'draft',
 state JSON NOT NULL,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 CONSTRAINT fk_live_v2_owner FOREIGN KEY (owner_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS live_v2_member (
 session_id BIGINT UNSIGNED NOT NULL,
 user_id BIGINT UNSIGNED NOT NULL,
 PRIMARY KEY (session_id, user_id),
 KEY idx_live_member_user (user_id, session_id),
 CONSTRAINT fk_live_v2_member_session FOREIGN KEY (session_id) REFERENCES live_v2_session(id),
 CONSTRAINT fk_live_v2_member_user FOREIGN KEY (user_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS live_v2_action (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
 session_id BIGINT UNSIGNED NOT NULL,
 user_id BIGINT UNSIGNED NOT NULL,
 command_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 request_hash CHAR(64) NOT NULL,
 action VARCHAR(32) NOT NULL,
 revision INT NOT NULL,
 audit JSON NOT NULL,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE KEY uq_live_v2_command (session_id, user_id, command_id),
 CONSTRAINT fk_live_v2_action_session FOREIGN KEY (session_id) REFERENCES live_v2_session(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS live_v2_opportunity (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
 session_id BIGINT UNSIGNED NOT NULL,
 first_user_id BIGINT UNSIGNED NOT NULL,
 second_user_id BIGINT UNSIGNED NOT NULL,
 expires_at DATETIME NOT NULL,
 application_id BIGINT UNSIGNED DEFAULT NULL,
 used_at DATETIME DEFAULT NULL,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE KEY uq_live_v2_pair (session_id, first_user_id, second_user_id),
 UNIQUE KEY uq_live_v2_application (application_id),
 CONSTRAINT fk_live_v2_opportunity_session FOREIGN KEY (session_id) REFERENCES live_v2_session(id),
 CONSTRAINT fk_live_v2_opportunity_first FOREIGN KEY (first_user_id) REFERENCES users(id),
 CONSTRAINT fk_live_v2_opportunity_second FOREIGN KEY (second_user_id) REFERENCES users(id),
 CONSTRAINT fk_live_v2_opportunity_apply FOREIGN KEY (application_id) REFERENCES match_apply(id),
 CONSTRAINT ck_live_v2_pair_order CHECK (first_user_id < second_user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS live_v2_report (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
 session_id BIGINT UNSIGNED NOT NULL,
 reporter_id BIGINT UNSIGNED NOT NULL,
 target_id BIGINT UNSIGNED NOT NULL,
 reason VARCHAR(500) NOT NULL,
 status VARCHAR(16) NOT NULL DEFAULT 'open',
 resolution VARCHAR(500) NOT NULL DEFAULT '',
 resolved_by BIGINT UNSIGNED DEFAULT NULL,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 resolved_at DATETIME DEFAULT NULL,
 CONSTRAINT fk_live_v2_report_session FOREIGN KEY (session_id) REFERENCES live_v2_session(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS live_v2_media_cleanup (
 id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
 session_id BIGINT UNSIGNED NOT NULL,
 room_id BIGINT UNSIGNED NOT NULL,
 task_id VARCHAR(128) DEFAULT NULL,
 done BOOLEAN NOT NULL DEFAULT FALSE,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE KEY uq_live_v2_retired_room (room_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
