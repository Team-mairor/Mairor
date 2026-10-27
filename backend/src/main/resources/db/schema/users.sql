-- users 테이블 (S15P31A306-205). 엔티티: users/entity/User.java
--
-- 운영 프로파일은 ddl-auto=validate 라서 이 테이블이 먼저 있어야 앱이 기동한다.
-- 적용 절차는 backend/README.md 의 "DB 스키마" 참고. (담당·시점은 확정 전)
-- Flyway 를 도입하면 db/migration/V<번호>__create_users.sql 로 옮긴다. 번호는 Flyway 담당과 확인한다.
--
-- 제약 이름 uk_users_email 은 User.EMAIL_UNIQUE 와 같아야 한다.
-- 가입 서비스가 이 이름으로 "이메일 중복"과 다른 제약 위반을 구분한다.
-- 엔티티와 이 파일이 맞는지는 UsersSchemaSqlTest 가 확인한다.
CREATE TABLE users (
    id            uuid                        NOT NULL,
    email         varchar(254)                NOT NULL,
    password_hash varchar(255),
    created_at    timestamp(6) with time zone NOT NULL,
    updated_at    timestamp(6) with time zone NOT NULL,
    CONSTRAINT users_pkey PRIMARY KEY (id),
    CONSTRAINT uk_users_email UNIQUE (email)
);
