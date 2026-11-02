-- users 테이블 (S15P31A306-205, 프로필·provider 추가 S15P31A306-214). 엔티티: users/entity/User.java
--
-- 운영 프로파일은 ddl-auto=validate 라서 이 테이블이 먼저 있어야 앱이 기동한다.
-- 적용 절차는 backend/README.md 의 "DB 스키마" 참고. (담당·시점은 확정 전)
-- Flyway 를 도입하면 db/migration/V<번호>__create_users.sql 로 옮긴다. 번호는 Flyway 담당과 확인한다.
--
-- 제약 이름 uk_users_email 은 User.EMAIL_UNIQUE 와 같아야 한다.
-- 가입 서비스가 이 이름으로 "이메일 중복"과 다른 제약 위반을 구분한다.
-- 엔티티와 이 파일이 맞는지는 UsersSchemaSqlTest 가 확인한다.
--
-- provider: LOCAL(자체 가입) | GOOGLE. gender: MALE | FEMALE.
-- nickname·name·phone·birth_date·gender 는 가입 때 선택 입력이라 NULL 을 허용한다. phone 은 유니크가 아니다.
-- email_verified_at: 이메일 인증 토큰으로 소유를 확인하고 가입한 시각 (인증 없이 가입했으면 NULL).
-- password_version: 비밀번호를 바꿀 때마다 1씩 오른다 (S15P31A306-210). 로그인이 비밀번호 재설정과 겹쳤는지 세션 발급 뒤에 확인하는 데 쓴다.
--   이미 users 테이블이 있는 DB 에는 이 파일을 다시 적용할 수 없으므로 아래 한 줄만 따로 적용한다.
--   ALTER TABLE users ADD COLUMN password_version integer NOT NULL DEFAULT 0;
CREATE TABLE users (
    id            uuid                        NOT NULL,
    email         varchar(254)                NOT NULL,
    password_hash varchar(255),
    provider      varchar(10)                 NOT NULL,
    nickname      varchar(20),
    name          varchar(50),
    phone         varchar(11),
    birth_date    date,
    gender        varchar(10),
    email_verified_at timestamp(6) with time zone,
    password_version integer                 NOT NULL DEFAULT 0,
    created_at    timestamp(6) with time zone NOT NULL,
    updated_at    timestamp(6) with time zone NOT NULL,
    CONSTRAINT users_pkey PRIMARY KEY (id),
    CONSTRAINT uk_users_email UNIQUE (email)
);

-- user_agreements 테이블 (S15P31A306-214). 엔티티: users/entity/UserAgreement.java
-- 회원별 약관 동의 기록. 회원당 약관 종류별로 한 행이고, 선택 약관(MARKETING)은 agreed=false 로도 남는다.
-- type: TERMS | PRIVACY | AGE_OVER_14 | MARKETING
CREATE TABLE user_agreements (
    id        uuid                        NOT NULL,
    user_id   uuid                        NOT NULL,
    type      varchar(30)                 NOT NULL,
    version   varchar(20)                 NOT NULL,
    agreed    boolean                     NOT NULL,
    agreed_at timestamp(6) with time zone NOT NULL,
    CONSTRAINT user_agreements_pkey PRIMARY KEY (id),
    CONSTRAINT fk_user_agreements_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT uk_user_agreements_user_type UNIQUE (user_id, type)
);

-- user_identities 테이블 (S15P31A306-208). 엔티티: users/entity/UserIdentity.java
-- 외부 로그인 제공자 계정과 회원의 연결. 지금은 GOOGLE 만 쓰고 provider_subject 는 ID 토큰의 sub 다.
-- 제공자 계정 하나는 회원 하나에만 연결된다 (uk_user_identities_provider_subject).
-- 이미 users 테이블이 있는 DB 에도 이 CREATE 문만 따로 적용하면 된다.
CREATE TABLE user_identities (
    id               uuid                        NOT NULL,
    user_id          uuid                        NOT NULL,
    provider         varchar(10)                 NOT NULL,
    provider_subject varchar(255)                NOT NULL,
    created_at       timestamp(6) with time zone NOT NULL,
    CONSTRAINT user_identities_pkey PRIMARY KEY (id),
    CONSTRAINT fk_user_identities_user FOREIGN KEY (user_id) REFERENCES users (id),
    CONSTRAINT uk_user_identities_provider_subject UNIQUE (provider, provider_subject)
);
