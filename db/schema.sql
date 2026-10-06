-- Production schema snapshot (structure only, no player data).
-- Source: live Railway Postgres via scripts/snapshot_prod_schema.sh
-- Taken: 2026-10-06. Refresh after every migration that ships.
-- CI builds its test database from this file, so tests run against the real schema.

--
-- PostgreSQL database dump
--


-- Dumped from database version 17.11 (Debian 17.11-1.pgdg13+2)
-- Dumped by pg_dump version 17.11 (Debian 17.11-0+deb13u1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: amcheck; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS amcheck WITH SCHEMA public;


--
-- Name: autoinc; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS autoinc WITH SCHEMA public;


--
-- Name: bloom; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS bloom WITH SCHEMA public;


--
-- Name: pageinspect; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pageinspect WITH SCHEMA public;


--
-- Name: pg_stat_statements; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_stat_statements WITH SCHEMA public;


--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: pg_visibility; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_visibility WITH SCHEMA public;


--
-- Name: pg_walinspect; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_walinspect WITH SCHEMA public;


--
-- Name: pgstattuple; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgstattuple WITH SCHEMA public;


--
-- Name: postgres_fdw; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS postgres_fdw WITH SCHEMA public;


--
-- Name: refint; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS refint WITH SCHEMA public;


--
-- Name: seg; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS seg WITH SCHEMA public;


--
-- Name: sslinfo; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS sslinfo WITH SCHEMA public;


--
-- Name: tablefunc; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS tablefunc WITH SCHEMA public;


--
-- Name: tcn; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS tcn WITH SCHEMA public;


--
-- Name: tsm_system_rows; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS tsm_system_rows WITH SCHEMA public;


--
-- Name: unaccent; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA public;


--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: xml2; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS xml2 WITH SCHEMA public;


--
-- Name: audit_province_delete(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.audit_province_delete() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  INSERT INTO admin_actions (actor, action, user_id, details)
  VALUES (
    current_setting('app.current_actor', true),
    'province_deleted',
    OLD.userId,
    jsonb_build_object('province', to_json(OLD))
  );
  RETURN OLD;
END;
$$;


--
-- Name: sync_province_population(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.sync_province_population() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE
    demo_sum BIGINT;
    old_demo_sum BIGINT;   -- was INTEGER; overflowed once a province's demo sum exceeded ~2.147B
    ratio NUMERIC;
BEGIN
    -- Check if demographics were changed
    IF (NEW.pop_children IS DISTINCT FROM OLD.pop_children) OR
       (NEW.pop_working  IS DISTINCT FROM OLD.pop_working)  OR
       (NEW.pop_elderly  IS DISTINCT FROM OLD.pop_elderly) THEN
        -- Demographics changed: recompute population from them
        NEW.population := NEW.pop_children + NEW.pop_working + NEW.pop_elderly;
    ELSIF NEW.population IS DISTINCT FROM OLD.population THEN
        -- Only population changed (no demographic columns touched):
        -- redistribute proportionally
        old_demo_sum := OLD.pop_children + OLD.pop_working + OLD.pop_elderly;
        IF old_demo_sum > 0 AND NEW.population > 0 THEN
            ratio := NEW.population::numeric / old_demo_sum;
            NEW.pop_children := GREATEST(0, ROUND(OLD.pop_children * ratio));
            NEW.pop_elderly  := GREATEST(0, ROUND(OLD.pop_elderly  * ratio));
            NEW.pop_working  := NEW.population - NEW.pop_children - NEW.pop_elderly;
        ELSIF NEW.population > 0 THEN
            -- No previous demographics: seed as children
            NEW.pop_children := NEW.population;
            NEW.pop_working  := 0;
            NEW.pop_elderly  := 0;
        ELSE
            NEW.pop_children := 0;
            NEW.pop_working  := 0;
            NEW.pop_elderly  := 0;
        END IF;
    END IF;

    RETURN NEW;
END;
$$;


--
-- Name: sync_province_population_insert(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.sync_province_population_insert() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.pop_children + NEW.pop_working + NEW.pop_elderly = 0 AND NEW.population > 0 THEN
        NEW.pop_children := NEW.population;
    END IF;
    RETURN NEW;
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: achievements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.achievements (
    key character varying(64) NOT NULL,
    name character varying(255) NOT NULL,
    description text NOT NULL,
    category character varying(64) NOT NULL,
    tier character varying(64) NOT NULL,
    icon character varying(255) NOT NULL
);


--
-- Name: admin_actions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.admin_actions (
    id integer NOT NULL,
    actor text,
    action text,
    user_id integer,
    details jsonb,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: admin_actions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.admin_actions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: admin_actions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.admin_actions_id_seq OWNED BY public.admin_actions.id;


--
-- Name: admin_user_controls; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.admin_user_controls (
    user_id integer NOT NULL,
    is_banned boolean DEFAULT false NOT NULL,
    ban_reason text,
    kick_pending boolean DEFAULT false NOT NULL,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: advertisements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.advertisements (
    id integer NOT NULL,
    user_id integer NOT NULL,
    image_url text NOT NULL,
    target_url text NOT NULL,
    ad_type text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    image_data text
);


--
-- Name: advertisements_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.advertisements_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: advertisements_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.advertisements_id_seq OWNED BY public.advertisements.id;


--
-- Name: assembly_effects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.assembly_effects (
    id integer NOT NULL,
    proposal_id integer NOT NULL,
    target_nation_id integer,
    target_currency_id integer,
    effect_type character varying(32) NOT NULL,
    currency_cap_amount bigint,
    active boolean DEFAULT true NOT NULL,
    expires_at timestamp without time zone
);


--
-- Name: assembly_effects_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.assembly_effects_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: assembly_effects_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.assembly_effects_id_seq OWNED BY public.assembly_effects.id;


--
-- Name: assembly_proposals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.assembly_proposals (
    id integer NOT NULL,
    proposer_id integer NOT NULL,
    type character varying(32) NOT NULL,
    target_nation_id integer,
    target_currency_id integer,
    currency_cap_amount bigint,
    text text,
    status character varying(16) DEFAULT 'open'::character varying NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    closes_at timestamp without time zone NOT NULL
);


--
-- Name: assembly_proposals_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.assembly_proposals_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: assembly_proposals_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.assembly_proposals_id_seq OWNED BY public.assembly_proposals.id;


--
-- Name: assembly_votes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.assembly_votes (
    id integer NOT NULL,
    proposal_id integer NOT NULL,
    voter_id integer NOT NULL,
    vote character varying(16) NOT NULL,
    weight double precision NOT NULL
);


--
-- Name: assembly_votes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.assembly_votes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: assembly_votes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.assembly_votes_id_seq OWNED BY public.assembly_votes.id;


--
-- Name: bmc_gem_purchases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bmc_gem_purchases (
    id bigint NOT NULL,
    user_id integer,
    gem_package_id bigint,
    bmc_transaction_id text NOT NULL,
    bmc_extra_line_id integer NOT NULL,
    claimed_username text,
    supporter_email text,
    supporter_name text,
    amount numeric,
    currency text,
    gems_granted bigint,
    status text DEFAULT 'credited'::text NOT NULL,
    credited_at timestamp with time zone,
    refunded_at timestamp with time zone,
    raw_event jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT bmc_gem_purchases_status_check CHECK ((status = ANY (ARRAY['credited'::text, 'refunded'::text, 'unmatched'::text])))
);


--
-- Name: bmc_gem_purchases_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.bmc_gem_purchases_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: bmc_gem_purchases_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.bmc_gem_purchases_id_seq OWNED BY public.bmc_gem_purchases.id;


--
-- Name: bonds; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bonds (
    id integer NOT NULL,
    issuer_id integer NOT NULL,
    lender_id integer,
    principal numeric NOT NULL,
    daily_interest_rate numeric NOT NULL,
    term_days integer NOT NULL,
    auto_escrow boolean DEFAULT false NOT NULL,
    escrowed_principal numeric DEFAULT 0 NOT NULL,
    status text DEFAULT 'listed'::text NOT NULL,
    default_strikes integer DEFAULT 0 NOT NULL,
    garnishment_owed numeric DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    funded_at timestamp with time zone,
    matures_at timestamp with time zone,
    last_tick_at timestamp with time zone,
    resolved_at timestamp with time zone,
    insurer_coalition_id integer,
    insurer_owed numeric DEFAULT 0 NOT NULL,
    insurance_paid numeric DEFAULT 0 NOT NULL,
    CONSTRAINT bonds_no_self_lending CHECK (((lender_id IS NULL) OR (lender_id <> issuer_id))),
    CONSTRAINT bonds_status_check CHECK ((status = ANY (ARRAY['listed'::text, 'active'::text, 'repaid'::text, 'defaulted'::text, 'cancelled'::text])))
);


--
-- Name: bonds_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.bonds_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: bonds_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.bonds_id_seq OWNED BY public.bonds.id;


--
-- Name: bounties; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bounties (
    id integer NOT NULL,
    target_id integer NOT NULL,
    poster_id integer NOT NULL,
    amount bigint NOT NULL,
    status character varying(20) DEFAULT 'open'::character varying NOT NULL,
    claimed_by integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    resolved_at timestamp with time zone,
    CONSTRAINT bounties_amount_check CHECK ((amount >= 1000)),
    CONSTRAINT bounties_status_check CHECK (((status)::text = ANY ((ARRAY['open'::character varying, 'claimed'::character varying, 'cancelled'::character varying])::text[])))
);


--
-- Name: bounties_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.bounties_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: bounties_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.bounties_id_seq OWNED BY public.bounties.id;


--
-- Name: building_dictionary; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.building_dictionary (
    building_id integer NOT NULL,
    name character varying(100) NOT NULL,
    display_name character varying(100) NOT NULL,
    category character varying(50) NOT NULL,
    base_cost bigint NOT NULL,
    effect_type character varying(50) NOT NULL,
    effect_value numeric(10,2) NOT NULL,
    maintenance_cost bigint DEFAULT 0,
    required_tech_id integer,
    description text,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT building_dictionary_base_cost_check CHECK ((base_cost > 0)),
    CONSTRAINT building_valid_category CHECK (((category)::text = ANY ((ARRAY['energy'::character varying, 'commerce'::character varying, 'civic'::character varying, 'military'::character varying, 'resource_production'::character varying, 'infrastructure'::character varying])::text[]))),
    CONSTRAINT building_valid_effect_type CHECK (((effect_type)::text = ANY ((ARRAY['resource_production'::character varying, 'population_growth'::character varying, 'happiness'::character varying, 'military_boost'::character varying, 'research_speed'::character varying, 'tax_income'::character varying, 'energy_production'::character varying, 'unit_capacity'::character varying, 'unit_production'::character varying])::text[])))
);


--
-- Name: building_dictionary_building_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.building_dictionary_building_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: building_dictionary_building_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.building_dictionary_building_id_seq OWNED BY public.building_dictionary.building_id;


--
-- Name: coalition_bond_insurance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.coalition_bond_insurance (
    coalition_id integer NOT NULL,
    user_id integer NOT NULL,
    added_by integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: coalition_invites; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.coalition_invites (
    id integer NOT NULL,
    coalition_id integer NOT NULL,
    invited_user_id integer NOT NULL,
    invited_by_user_id integer NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying,
    created_at timestamp with time zone DEFAULT now(),
    expires_at timestamp with time zone DEFAULT (now() + '30 days'::interval),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT coalition_invites_status_check CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'accepted'::character varying, 'rejected'::character varying, 'revoked'::character varying])::text[])))
);


--
-- Name: coalition_invites_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.coalition_invites_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: coalition_invites_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.coalition_invites_id_seq OWNED BY public.coalition_invites.id;


--
-- Name: coalition_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.coalition_members (
    user_id integer NOT NULL,
    coalition_id integer NOT NULL,
    role character varying(40) DEFAULT 'member'::character varying NOT NULL,
    joined_at timestamp with time zone DEFAULT now(),
    CONSTRAINT coalition_valid_role CHECK (((role)::text = ANY ((ARRAY['founder'::character varying, 'leader'::character varying, 'officer'::character varying, 'member'::character varying])::text[])))
);


--
-- Name: coalition_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.coalition_messages (
    id bigint NOT NULL,
    coalition_id integer NOT NULL,
    sender_id integer NOT NULL,
    content character varying(1000) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: coalition_messages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.coalition_messages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: coalition_messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.coalition_messages_id_seq OWNED BY public.coalition_messages.id;


--
-- Name: coalitions_legacy; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.coalitions_legacy (
    colid integer NOT NULL,
    userid integer NOT NULL,
    role character varying(40) DEFAULT 'member'::character varying NOT NULL,
    joined_at timestamp with time zone DEFAULT now()
);


--
-- Name: coalitions_normalized; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.coalitions_normalized (
    coalition_id integer NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    bank_balance bigint DEFAULT 0 NOT NULL,
    founder_id integer,
    created_at timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true,
    CONSTRAINT coalitions_normalized_bank_balance_check CHECK ((bank_balance >= 0))
);


--
-- Name: coalitions_normalized_coalition_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.coalitions_normalized_coalition_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: coalitions_normalized_coalition_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.coalitions_normalized_coalition_id_seq OWNED BY public.coalitions_normalized.coalition_id;


--
-- Name: col_applications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.col_applications (
    id integer NOT NULL,
    colid integer NOT NULL,
    userid integer NOT NULL,
    message text,
    status text DEFAULT 'pending'::text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: col_applications_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.col_applications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: col_applications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.col_applications_id_seq OWNED BY public.col_applications.id;


--
-- Name: col_bank_contributions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.col_bank_contributions (
    coalition_id integer NOT NULL,
    user_id integer NOT NULL,
    resource text NOT NULL,
    total_deposited bigint DEFAULT 0 NOT NULL,
    total_withdrawn bigint DEFAULT 0
);


--
-- Name: col_bank_recurring_trade_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.col_bank_recurring_trade_runs (
    id bigint NOT NULL,
    recurring_trade_id integer NOT NULL,
    scheduled_for timestamp with time zone NOT NULL,
    executed_at timestamp with time zone DEFAULT now() NOT NULL,
    outcome text NOT NULL,
    CONSTRAINT col_bank_recurring_trade_runs_outcome_check CHECK ((outcome = ANY (ARRAY['success'::text, 'member_short'::text, 'bank_short'::text])))
);


--
-- Name: col_bank_recurring_trade_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.col_bank_recurring_trade_runs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: col_bank_recurring_trade_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.col_bank_recurring_trade_runs_id_seq OWNED BY public.col_bank_recurring_trade_runs.id;


--
-- Name: col_bank_recurring_trades; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.col_bank_recurring_trades (
    id integer NOT NULL,
    coalition_id integer NOT NULL,
    user_id integer NOT NULL,
    give_resource text NOT NULL,
    give_amount bigint NOT NULL,
    want_resource text NOT NULL,
    want_amount bigint NOT NULL,
    interval_hours integer NOT NULL,
    max_repetitions integer,
    repetitions_done integer DEFAULT 0 NOT NULL,
    consecutive_failures integer DEFAULT 0 NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    note text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    approved_at timestamp with time zone,
    approved_by integer,
    next_execution_at timestamp with time zone,
    last_executed_at timestamp with time zone,
    ended_at timestamp with time zone,
    ended_by integer,
    CONSTRAINT col_bank_recurring_trades_distinct_resources CHECK ((give_resource <> want_resource)),
    CONSTRAINT col_bank_recurring_trades_give_amount_check CHECK ((give_amount > 0)),
    CONSTRAINT col_bank_recurring_trades_interval_hours_check CHECK ((interval_hours > 0)),
    CONSTRAINT col_bank_recurring_trades_max_repetitions_check CHECK (((max_repetitions IS NULL) OR (max_repetitions > 0))),
    CONSTRAINT col_bank_recurring_trades_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'active'::text, 'paused'::text, 'completed'::text, 'cancelled'::text, 'declined'::text]))),
    CONSTRAINT col_bank_recurring_trades_want_amount_check CHECK ((want_amount > 0))
);


--
-- Name: col_bank_recurring_trades_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.col_bank_recurring_trades_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: col_bank_recurring_trades_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.col_bank_recurring_trades_id_seq OWNED BY public.col_bank_recurring_trades.id;


--
-- Name: col_bank_trades; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.col_bank_trades (
    id integer NOT NULL,
    coalition_id integer NOT NULL,
    user_id integer NOT NULL,
    give_resource text NOT NULL,
    give_amount bigint NOT NULL,
    want_resource text NOT NULL,
    want_amount bigint NOT NULL,
    note text,
    status text DEFAULT 'pending'::text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    resolved_at timestamp with time zone,
    resolved_by integer,
    CONSTRAINT col_bank_trades_distinct_resources CHECK ((give_resource <> want_resource)),
    CONSTRAINT col_bank_trades_give_amount_check CHECK ((give_amount > 0)),
    CONSTRAINT col_bank_trades_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'accepted'::text, 'declined'::text, 'cancelled'::text]))),
    CONSTRAINT col_bank_trades_want_amount_check CHECK ((want_amount > 0))
);


--
-- Name: col_bank_trades_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.col_bank_trades_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: col_bank_trades_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.col_bank_trades_id_seq OWNED BY public.col_bank_trades.id;


--
-- Name: col_bank_transactions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.col_bank_transactions (
    id bigint NOT NULL,
    coalition_id integer NOT NULL,
    user_id integer NOT NULL,
    actor_id integer NOT NULL,
    resource text NOT NULL,
    amount bigint NOT NULL,
    direction text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    kind text DEFAULT 'manual'::text NOT NULL,
    CONSTRAINT col_bank_transactions_direction_check CHECK ((direction = ANY (ARRAY['deposit'::text, 'withdraw'::text])))
);


--
-- Name: col_bank_transactions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.col_bank_transactions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: col_bank_transactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.col_bank_transactions_id_seq OWNED BY public.col_bank_transactions.id;


--
-- Name: col_role_names; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.col_role_names (
    coalition_id integer NOT NULL,
    role text NOT NULL,
    display_name text NOT NULL
);


--
-- Name: colbanks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.colbanks (
    colid integer NOT NULL,
    money bigint DEFAULT 0 NOT NULL,
    rations bigint DEFAULT 0 NOT NULL,
    oil bigint DEFAULT 0 NOT NULL,
    coal bigint DEFAULT 0 NOT NULL,
    uranium bigint DEFAULT 0 NOT NULL,
    bauxite bigint DEFAULT 0 NOT NULL,
    iron bigint DEFAULT 0 NOT NULL,
    lead bigint DEFAULT 0 NOT NULL,
    copper bigint DEFAULT 0 NOT NULL,
    lumber bigint DEFAULT 0 NOT NULL,
    components bigint DEFAULT 0 NOT NULL,
    steel bigint DEFAULT 0 NOT NULL,
    consumer_goods bigint DEFAULT 0 NOT NULL,
    aluminium bigint DEFAULT 0 NOT NULL,
    gasoline bigint DEFAULT 0 NOT NULL,
    ammunition bigint DEFAULT 0 NOT NULL,
    silver bigint DEFAULT 0,
    diamonds bigint DEFAULT 0,
    bullion bigint DEFAULT 0
);


--
-- Name: colbanksrequests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.colbanksrequests (
    id integer NOT NULL,
    reqid integer NOT NULL,
    colid integer NOT NULL,
    amount bigint NOT NULL,
    resource character varying(30)
);


--
-- Name: colbanksrequests_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.colbanksrequests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: colbanksrequests_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.colbanksrequests_id_seq OWNED BY public.colbanksrequests.id;


--
-- Name: colnames; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.colnames (
    id integer NOT NULL,
    description character varying(2000),
    type character varying(12) NOT NULL,
    flag character varying(40),
    name character varying(40) NOT NULL,
    date character varying(10) NOT NULL,
    flag_data text,
    recruiting boolean DEFAULT false,
    name_changes_used integer DEFAULT 0,
    tax_rate integer DEFAULT 0 NOT NULL,
    share_builds_default boolean DEFAULT false NOT NULL,
    bank_require_requests boolean DEFAULT false NOT NULL,
    bank_self_approve boolean DEFAULT true NOT NULL,
    info_access jsonb,
    CONSTRAINT chk_tax_rate CHECK (((tax_rate >= 0) AND (tax_rate <= 20)))
);


--
-- Name: colnames_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.colnames_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: colnames_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.colnames_id_seq OWNED BY public.colnames.id;


--
-- Name: cosmetics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.cosmetics (
    id bigint NOT NULL,
    slug text NOT NULL,
    name text NOT NULL,
    cosmetic_type text DEFAULT 'background'::text NOT NULL,
    price_gems bigint NOT NULL,
    css_class text,
    preview_image_url text,
    is_active boolean DEFAULT true NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    value text,
    CONSTRAINT cosmetics_cosmetic_type_check CHECK ((cosmetic_type = ANY (ARRAY['background'::text, 'name_color'::text, 'badge'::text, 'title'::text, 'country_border'::text]))),
    CONSTRAINT cosmetics_price_gems_check CHECK ((price_gems > 0))
);


--
-- Name: cosmetics_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.cosmetics_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: cosmetics_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.cosmetics_id_seq OWNED BY public.cosmetics.id;


--
-- Name: currency_holdings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.currency_holdings (
    user_id integer NOT NULL,
    issuer_id integer NOT NULL,
    amount numeric(18,2) DEFAULT 0 NOT NULL,
    CONSTRAINT currency_holdings_amount_check CHECK ((amount >= (0)::numeric)),
    CONSTRAINT currency_holdings_not_own CHECK ((user_id <> issuer_id))
);


--
-- Name: currency_market_offers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.currency_market_offers (
    offer_id integer NOT NULL,
    user_id integer NOT NULL,
    issuer_id integer NOT NULL,
    type text NOT NULL,
    amount numeric(18,2) NOT NULL,
    price_gold numeric(12,2) NOT NULL,
    gold_escrow bigint DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT currency_market_offers_amount_check CHECK ((amount > (0)::numeric)),
    CONSTRAINT currency_market_offers_gold_escrow_check CHECK ((gold_escrow >= 0)),
    CONSTRAINT currency_market_offers_price_gold_check CHECK ((price_gold > (0)::numeric)),
    CONSTRAINT currency_market_offers_type_check CHECK ((type = ANY (ARRAY['buy'::text, 'sell'::text])))
);


--
-- Name: currency_market_offers_offer_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.currency_market_offers_offer_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: currency_market_offers_offer_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.currency_market_offers_offer_id_seq OWNED BY public.currency_market_offers.offer_id;


--
-- Name: currency_market_trades; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.currency_market_trades (
    id integer NOT NULL,
    issuer_id integer NOT NULL,
    buyer_id integer,
    seller_id integer,
    amount numeric(18,2) NOT NULL,
    price_gold numeric(12,2) NOT NULL,
    gold_total bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: currency_market_trades_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.currency_market_trades_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: currency_market_trades_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.currency_market_trades_id_seq OWNED BY public.currency_market_trades.id;


--
-- Name: currency_union_applications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.currency_union_applications (
    union_id integer NOT NULL,
    user_id integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: currency_union_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.currency_union_members (
    user_id integer NOT NULL,
    union_id integer NOT NULL,
    joined_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: currency_unions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.currency_unions (
    id integer NOT NULL,
    name character varying(60) NOT NULL,
    currency_name character varying(40) NOT NULL,
    founder_id integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: currency_unions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.currency_unions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: currency_unions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.currency_unions_id_seq OWNED BY public.currency_unions.id;


--
-- Name: devlog_entries; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.devlog_entries (
    id bigint NOT NULL,
    author_id integer NOT NULL,
    title character varying(200) NOT NULL,
    body character varying(4000) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: devlog_entries_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.devlog_entries_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: devlog_entries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.devlog_entries_id_seq OWNED BY public.devlog_entries.id;


--
-- Name: direct_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.direct_messages (
    id bigint NOT NULL,
    sender_id integer NOT NULL,
    recipient_id integer NOT NULL,
    content character varying(1000) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    read_at timestamp with time zone,
    CONSTRAINT direct_messages_no_self_message CHECK ((sender_id <> recipient_id))
);


--
-- Name: direct_messages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.direct_messages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: direct_messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.direct_messages_id_seq OWNED BY public.direct_messages.id;


--
-- Name: discord_bad_words; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discord_bad_words (
    guild_id character varying(32) NOT NULL,
    word character varying(128) NOT NULL
);


--
-- Name: discord_custom_commands; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discord_custom_commands (
    id integer NOT NULL,
    guild_id character varying(32) NOT NULL,
    trigger_word character varying(64) NOT NULL,
    response_type character varying(16) DEFAULT 'text'::character varying NOT NULL,
    response_text text,
    embed_title character varying(256),
    embed_color character varying(7),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: discord_custom_commands_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.discord_custom_commands_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: discord_custom_commands_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.discord_custom_commands_id_seq OWNED BY public.discord_custom_commands.id;


--
-- Name: discord_giveaways; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discord_giveaways (
    id integer NOT NULL,
    guild_id character varying(32) NOT NULL,
    channel_id character varying(32) NOT NULL,
    message_id character varying(32),
    prize text NOT NULL,
    winners_count integer DEFAULT 1 NOT NULL,
    ends_at timestamp with time zone NOT NULL,
    ended boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: discord_giveaways_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.discord_giveaways_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: discord_giveaways_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.discord_giveaways_id_seq OWNED BY public.discord_giveaways.id;


--
-- Name: discord_guild_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discord_guild_settings (
    guild_id character varying(32) NOT NULL,
    coalition_id integer,
    registered_role_id character varying(32),
    bank_alert_channel_id character varying(32),
    war_alert_channel_id character varying(32),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    panel_readme_channel_id character varying(32),
    panel_leaderboard_channel_id character varying(32),
    panel_war_feed_channel_id character varying(32),
    panel_inspector_channel_id character varying(32),
    panel_world_channel_id character varying(32),
    panel_alerts_channel_id character varying(32),
    panels_enabled boolean DEFAULT false NOT NULL,
    panels_refresh_minutes integer DEFAULT 15 NOT NULL,
    panel_analytics_channel_id character varying(32)
);


--
-- Name: discord_level_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discord_level_config (
    guild_id character varying(32) NOT NULL,
    xp_per_message integer DEFAULT 15 NOT NULL,
    xp_cooldown_seconds integer DEFAULT 60 NOT NULL,
    xp_per_voice_minute integer DEFAULT 5 NOT NULL,
    level_up_channel_id character varying(32),
    level_up_enabled boolean DEFAULT true NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: discord_level_roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discord_level_roles (
    guild_id character varying(32) NOT NULL,
    level integer NOT NULL,
    role_id character varying(32) NOT NULL
);


--
-- Name: discord_link_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discord_link_codes (
    code character varying(16) NOT NULL,
    user_id integer NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    used_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: discord_logging_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discord_logging_config (
    guild_id character varying(32) NOT NULL,
    log_channel_id character varying(32),
    log_message_edit boolean DEFAULT true NOT NULL,
    log_message_delete boolean DEFAULT true NOT NULL,
    log_member_join boolean DEFAULT true NOT NULL,
    log_member_leave boolean DEFAULT true NOT NULL,
    log_member_ban boolean DEFAULT true NOT NULL,
    log_member_timeout boolean DEFAULT true NOT NULL,
    log_role_changes boolean DEFAULT false NOT NULL,
    log_channel_changes boolean DEFAULT false NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: discord_mod_cases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discord_mod_cases (
    id integer NOT NULL,
    guild_id character varying(32) NOT NULL,
    action character varying(16) NOT NULL,
    target_user_id character varying(32) NOT NULL,
    moderator_user_id character varying(32) NOT NULL,
    reason text,
    duration_minutes integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: discord_mod_cases_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.discord_mod_cases_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: discord_mod_cases_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.discord_mod_cases_id_seq OWNED BY public.discord_mod_cases.id;


--
-- Name: discord_moderation_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discord_moderation_config (
    guild_id character varying(32) NOT NULL,
    log_channel_id character varying(32),
    filter_spam_enabled boolean DEFAULT false NOT NULL,
    filter_spam_message_limit integer DEFAULT 5 NOT NULL,
    filter_spam_interval_seconds integer DEFAULT 5 NOT NULL,
    filter_invites_enabled boolean DEFAULT false NOT NULL,
    filter_mass_mentions_enabled boolean DEFAULT false NOT NULL,
    filter_mass_mentions_limit integer DEFAULT 5 NOT NULL,
    filter_bad_words_enabled boolean DEFAULT false NOT NULL,
    filter_action character varying(16) DEFAULT 'delete_warn'::character varying NOT NULL,
    filter_timeout_minutes integer DEFAULT 10 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: discord_panel_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discord_panel_messages (
    guild_id character varying(32) NOT NULL,
    panel_key character varying(32) NOT NULL,
    channel_id character varying(32) NOT NULL,
    message_id character varying(32) NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: discord_reaction_roles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discord_reaction_roles (
    guild_id character varying(32) NOT NULL,
    message_id character varying(32) NOT NULL,
    emoji character varying(64) NOT NULL,
    role_id character varying(32) NOT NULL
);


--
-- Name: discord_role_aliases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discord_role_aliases (
    guild_id character varying(32) NOT NULL,
    alias character varying(64) NOT NULL,
    discord_role_id character varying(32) NOT NULL
);


--
-- Name: discord_starboard_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discord_starboard_config (
    guild_id character varying(32) NOT NULL,
    enabled boolean DEFAULT false NOT NULL,
    channel_id character varying(32),
    emoji character varying(64) DEFAULT '⭐'::character varying NOT NULL,
    threshold integer DEFAULT 3 NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: discord_starboard_posts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discord_starboard_posts (
    guild_id character varying(32) NOT NULL,
    source_message_id character varying(32) NOT NULL,
    source_channel_id character varying(32) NOT NULL,
    starboard_message_id character varying(32) NOT NULL,
    star_count integer DEFAULT 0 NOT NULL
);


--
-- Name: discord_suggestions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discord_suggestions (
    id integer NOT NULL,
    guild_id character varying(32) NOT NULL,
    author_user_id character varying(32) NOT NULL,
    channel_id character varying(32) NOT NULL,
    message_id character varying(32),
    content text NOT NULL,
    status character varying(16) DEFAULT 'pending'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    decided_at timestamp with time zone,
    decided_by_user_id character varying(32)
);


--
-- Name: discord_suggestions_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discord_suggestions_config (
    guild_id character varying(32) NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    channel_id character varying(32),
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: discord_suggestions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.discord_suggestions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: discord_suggestions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.discord_suggestions_id_seq OWNED BY public.discord_suggestions.id;


--
-- Name: discord_ticket_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discord_ticket_config (
    guild_id character varying(32) NOT NULL,
    enabled boolean DEFAULT false NOT NULL,
    ticket_channel_id character varying(32),
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: discord_tickets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discord_tickets (
    id integer NOT NULL,
    guild_id character varying(32) NOT NULL,
    opener_user_id character varying(32) NOT NULL,
    thread_id character varying(32) NOT NULL,
    status character varying(16) DEFAULT 'open'::character varying NOT NULL,
    opened_at timestamp with time zone DEFAULT now() NOT NULL,
    closed_at timestamp with time zone,
    closed_by_user_id character varying(32)
);


--
-- Name: discord_tickets_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.discord_tickets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: discord_tickets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.discord_tickets_id_seq OWNED BY public.discord_tickets.id;


--
-- Name: discord_user_xp; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discord_user_xp (
    guild_id character varying(32) NOT NULL,
    user_id character varying(32) NOT NULL,
    xp integer DEFAULT 0 NOT NULL,
    level integer DEFAULT 0 NOT NULL,
    last_xp_at timestamp with time zone
);


--
-- Name: discord_welcome_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.discord_welcome_config (
    guild_id character varying(32) NOT NULL,
    enabled boolean DEFAULT false NOT NULL,
    channel_id character varying(32),
    message_template text,
    dm_enabled boolean DEFAULT false NOT NULL,
    dm_template text,
    auto_role_ids text[] DEFAULT '{}'::text[] NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: forum_replies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.forum_replies (
    id bigint NOT NULL,
    thread_id bigint NOT NULL,
    author_id integer NOT NULL,
    content character varying(2000) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: forum_replies_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.forum_replies_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: forum_replies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.forum_replies_id_seq OWNED BY public.forum_replies.id;


--
-- Name: forum_threads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.forum_threads (
    id bigint NOT NULL,
    author_id integer NOT NULL,
    title character varying(200) NOT NULL,
    body character varying(4000) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    last_activity_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: forum_threads_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.forum_threads_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: forum_threads_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.forum_threads_id_seq OWNED BY public.forum_threads.id;


--
-- Name: game_economy_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.game_economy_snapshots (
    id integer NOT NULL,
    snapshot_time timestamp with time zone DEFAULT now(),
    resource_name text NOT NULL,
    total_quantity bigint DEFAULT 0 NOT NULL,
    player_count integer DEFAULT 0 NOT NULL
);


--
-- Name: game_economy_snapshots_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.game_economy_snapshots_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: game_economy_snapshots_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.game_economy_snapshots_id_seq OWNED BY public.game_economy_snapshots.id;


--
-- Name: game_tick_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.game_tick_logs (
    tick_id bigint NOT NULL,
    tick_type character varying(40) DEFAULT 'global_tick'::character varying NOT NULL,
    status character varying(20) DEFAULT 'running'::character varying NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    finished_at timestamp with time zone,
    users_processed integer DEFAULT 0 NOT NULL,
    production_entries integer DEFAULT 0 NOT NULL,
    consumption_entries integer DEFAULT 0 NOT NULL,
    total_production bigint DEFAULT 0 NOT NULL,
    total_consumption bigint DEFAULT 0 NOT NULL,
    total_deserted_units bigint DEFAULT 0 NOT NULL,
    error_message text,
    CONSTRAINT game_tick_logs_nonnegative_counts CHECK (((users_processed >= 0) AND (production_entries >= 0) AND (consumption_entries >= 0) AND (total_production >= 0) AND (total_consumption >= 0) AND (total_deserted_units >= 0))),
    CONSTRAINT game_tick_logs_valid_status CHECK (((status)::text = ANY ((ARRAY['running'::character varying, 'completed'::character varying, 'failed'::character varying])::text[])))
);


--
-- Name: game_tick_logs_tick_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.game_tick_logs_tick_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: game_tick_logs_tick_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.game_tick_logs_tick_id_seq OWNED BY public.game_tick_logs.tick_id;


--
-- Name: gem_packages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.gem_packages (
    id bigint NOT NULL,
    name text NOT NULL,
    gems_granted bigint NOT NULL,
    price_cents integer NOT NULL,
    currency text DEFAULT 'usd'::text NOT NULL,
    stripe_price_id text,
    is_active boolean DEFAULT true NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    bmc_extra_id integer,
    bmc_price_cents integer,
    CONSTRAINT gem_packages_gems_granted_check CHECK ((gems_granted > 0)),
    CONSTRAINT gem_packages_price_cents_check CHECK ((price_cents > 0))
);


--
-- Name: gem_packages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.gem_packages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: gem_packages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.gem_packages_id_seq OWNED BY public.gem_packages.id;


--
-- Name: gem_purchases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.gem_purchases (
    id bigint NOT NULL,
    user_id integer NOT NULL,
    gem_package_id bigint NOT NULL,
    stripe_checkout_session_id text,
    stripe_payment_intent_id text,
    amount_cents integer NOT NULL,
    currency text NOT NULL,
    gems_granted bigint NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    credited_at timestamp with time zone,
    refunded_at timestamp with time zone,
    raw_event jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT gem_purchases_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'paid'::text, 'credited'::text, 'failed'::text, 'refunded'::text, 'chargeback'::text])))
);


--
-- Name: gem_purchases_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.gem_purchases_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: gem_purchases_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.gem_purchases_id_seq OWNED BY public.gem_purchases.id;


--
-- Name: global_chat_messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.global_chat_messages (
    id bigint NOT NULL,
    sender_id integer NOT NULL,
    content character varying(1000) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: global_chat_messages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.global_chat_messages_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: global_chat_messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.global_chat_messages_id_seq OWNED BY public.global_chat_messages.id;


--
-- Name: global_market; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.global_market (
    market_id integer NOT NULL,
    seller_id integer NOT NULL,
    resource_id integer NOT NULL,
    quantity bigint NOT NULL,
    price_per_unit numeric(15,2) NOT NULL,
    offer_type character varying(20) DEFAULT 'sell'::character varying NOT NULL,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    expires_at timestamp with time zone,
    fulfilled_by integer,
    fulfilled_at timestamp with time zone,
    CONSTRAINT global_market_price_per_unit_check CHECK ((price_per_unit > (0)::numeric)),
    CONSTRAINT global_market_quantity_check CHECK ((quantity > 0)),
    CONSTRAINT market_valid_offer_type CHECK (((offer_type)::text = ANY ((ARRAY['sell'::character varying, 'buy'::character varying, 'trade'::character varying])::text[]))),
    CONSTRAINT market_valid_status CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'fulfilled'::character varying, 'cancelled'::character varying, 'expired'::character varying])::text[])))
);


--
-- Name: global_market_market_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.global_market_market_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: global_market_market_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.global_market_market_id_seq OWNED BY public.global_market.market_id;


--
-- Name: identity_diagnostic_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.identity_diagnostic_log (
    id bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    route text NOT NULL,
    session_user_id integer,
    cookie_fp text,
    ip text,
    worker_pid integer,
    thread_id bigint,
    cache_hit boolean,
    severity text DEFAULT 'info'::text NOT NULL,
    detail jsonb
);


--
-- Name: identity_diagnostic_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.identity_diagnostic_log_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: identity_diagnostic_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.identity_diagnostic_log_id_seq OWNED BY public.identity_diagnostic_log.id;


--
-- Name: interactive_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.interactive_events (
    id integer NOT NULL,
    user_id integer,
    event_def_id character varying,
    created_at timestamp without time zone DEFAULT now(),
    resolved_at timestamp without time zone,
    chosen_option_index integer,
    province_id integer
);


--
-- Name: interactive_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.interactive_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: interactive_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.interactive_events_id_seq OWNED BY public.interactive_events.id;


--
-- Name: keys; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.keys (
    key character varying(36)
);


--
-- Name: login_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.login_events (
    id bigint NOT NULL,
    user_id integer NOT NULL,
    ip character varying(45),
    fingerprint text,
    auth_type character varying(20),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: login_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.login_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: login_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.login_events_id_seq OWNED BY public.login_events.id;


--
-- Name: login_verifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.login_verifications (
    id bigint NOT NULL,
    user_id integer NOT NULL,
    token character varying(64) NOT NULL,
    ip character varying(45),
    fingerprint text,
    auth_type character varying(20),
    delivery_method character varying(20),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    consumed_at timestamp with time zone,
    delivered boolean
);


--
-- Name: login_verifications_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.login_verifications_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: login_verifications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.login_verifications_id_seq OWNED BY public.login_verifications.id;


--
-- Name: map_combat_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.map_combat_log (
    id integer NOT NULL,
    attacker_id integer NOT NULL,
    defender_id integer,
    province_id integer NOT NULL,
    attacker_soldiers integer DEFAULT 0 NOT NULL,
    defender_soldiers integer DEFAULT 0 NOT NULL,
    result character varying(20) DEFAULT 'attacker_won'::character varying NOT NULL,
    occurred_at timestamp with time zone DEFAULT now()
);


--
-- Name: map_combat_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.map_combat_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: map_combat_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.map_combat_log_id_seq OWNED BY public.map_combat_log.id;


--
-- Name: map_objects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.map_objects (
    id integer NOT NULL,
    x integer NOT NULL,
    y integer NOT NULL,
    type character varying(50) NOT NULL,
    subtype character varying(50),
    quantity bigint DEFAULT 0,
    owner_id integer,
    last_update bigint
);


--
-- Name: map_objects_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.map_objects_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: map_objects_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.map_objects_id_seq OWNED BY public.map_objects.id;


--
-- Name: map_unit_deployments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.map_unit_deployments (
    id integer NOT NULL,
    province_id integer NOT NULL,
    user_id integer NOT NULL,
    soldiers integer DEFAULT 0 NOT NULL,
    deployed_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT map_unit_deployments_soldiers_check CHECK ((soldiers >= 0))
);


--
-- Name: map_unit_deployments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.map_unit_deployments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: map_unit_deployments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.map_unit_deployments_id_seq OWNED BY public.map_unit_deployments.id;


--
-- Name: marches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.marches (
    id integer NOT NULL,
    user_id integer NOT NULL,
    target_id integer,
    target_type character varying(50),
    start_x integer NOT NULL,
    start_y integer NOT NULL,
    target_x integer NOT NULL,
    target_y integer NOT NULL,
    start_time bigint NOT NULL,
    arrival_time bigint NOT NULL,
    return_time bigint,
    status character varying(50) DEFAULT 'marching'::character varying,
    troops jsonb,
    resources jsonb
);


--
-- Name: marches_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.marches_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: marches_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.marches_id_seq OWNED BY public.marches.id;


--
-- Name: market_auto_order_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.market_auto_order_log (
    id integer NOT NULL,
    auto_order_id integer NOT NULL,
    units bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: market_auto_order_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.market_auto_order_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: market_auto_order_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.market_auto_order_log_id_seq OWNED BY public.market_auto_order_log.id;


--
-- Name: market_auto_orders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.market_auto_orders (
    id integer NOT NULL,
    user_id integer NOT NULL,
    type text NOT NULL,
    resource text NOT NULL,
    price integer NOT NULL,
    currency_id integer,
    reserve_limit bigint,
    max_offer bigint,
    max_per_day bigint,
    alert_pct integer,
    active boolean DEFAULT true NOT NULL,
    offer_id integer,
    last_run_at timestamp with time zone,
    last_status text,
    last_alert_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT market_auto_orders_alert_pct_check CHECK (((alert_pct >= 1) AND (alert_pct <= 1000))),
    CONSTRAINT market_auto_orders_check CHECK (((max_offer IS NOT NULL) OR (max_per_day IS NOT NULL))),
    CONSTRAINT market_auto_orders_max_offer_check CHECK ((max_offer > 0)),
    CONSTRAINT market_auto_orders_max_per_day_check CHECK ((max_per_day > 0)),
    CONSTRAINT market_auto_orders_price_check CHECK ((price > 0)),
    CONSTRAINT market_auto_orders_reserve_limit_check CHECK ((reserve_limit >= 0)),
    CONSTRAINT market_auto_orders_type_check CHECK ((type = ANY (ARRAY['buy'::text, 'sell'::text])))
);


--
-- Name: market_auto_orders_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.market_auto_orders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: market_auto_orders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.market_auto_orders_id_seq OWNED BY public.market_auto_orders.id;


--
-- Name: market_embargoes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.market_embargoes (
    embargoer_id integer NOT NULL,
    embargoed_id integer NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT market_embargoes_check CHECK ((embargoer_id <> embargoed_id))
);


--
-- Name: market_fills; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.market_fills (
    id integer NOT NULL,
    offer_id integer NOT NULL,
    resource text NOT NULL,
    amount bigint NOT NULL,
    price integer NOT NULL,
    currency_id integer,
    gold_price integer NOT NULL,
    seller_id integer,
    buyer_id integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: market_fills_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.market_fills_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: market_fills_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.market_fills_id_seq OWNED BY public.market_fills.id;


--
-- Name: market_preferences; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.market_preferences (
    user_id integer NOT NULL,
    default_resource text,
    hide_unavailable boolean DEFAULT false NOT NULL,
    hide_exchange boolean DEFAULT false NOT NULL,
    hide_embargoed boolean DEFAULT true NOT NULL,
    currency_mode text DEFAULT 'all'::text NOT NULL,
    currency_id integer,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT market_preferences_currency_mode_check CHECK ((currency_mode = ANY (ARRAY['all'::text, 'gold'::text, 'currency'::text])))
);


--
-- Name: military; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.military (
    id integer NOT NULL,
    soldiers bigint DEFAULT 0 NOT NULL,
    artillery bigint DEFAULT 0 NOT NULL,
    tanks bigint DEFAULT 0 NOT NULL,
    bombers bigint DEFAULT 0 NOT NULL,
    fighters bigint DEFAULT 0 NOT NULL,
    apaches bigint DEFAULT 0 NOT NULL,
    spies bigint DEFAULT 0 NOT NULL,
    icbms bigint DEFAULT 0 NOT NULL,
    nukes bigint DEFAULT 0 NOT NULL,
    destroyers bigint DEFAULT 0 NOT NULL,
    cruisers bigint DEFAULT 0 NOT NULL,
    submarines bigint DEFAULT 0 NOT NULL,
    default_defense text DEFAULT 'soldiers,tanks,artillery'::text NOT NULL,
    manpower bigint DEFAULT 100,
    army_tradition real DEFAULT 0.2,
    defcon bigint DEFAULT 1 NOT NULL
);


--
-- Name: nation_revenue_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nation_revenue_history (
    id bigint NOT NULL,
    user_id integer NOT NULL,
    recorded_at timestamp with time zone DEFAULT now() NOT NULL,
    category character varying(32) NOT NULL,
    amount bigint NOT NULL
);


--
-- Name: nation_revenue_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.nation_revenue_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: nation_revenue_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.nation_revenue_history_id_seq OWNED BY public.nation_revenue_history.id;


--
-- Name: nation_treaties; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nation_treaties (
    id integer NOT NULL,
    sender_id integer NOT NULL,
    recipient_id integer NOT NULL,
    treaty_type character varying(50) NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: nation_treaties_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.nation_treaties_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: nation_treaties_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.nation_treaties_id_seq OWNED BY public.nation_treaties.id;


--
-- Name: national_currency_conversions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.national_currency_conversions (
    id integer NOT NULL,
    user_id integer NOT NULL,
    direction text NOT NULL,
    gold_amount numeric(18,2) NOT NULL,
    currency_amount numeric(18,2) NOT NULL,
    rate numeric(18,2) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: national_currency_conversions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.national_currency_conversions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: national_currency_conversions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.national_currency_conversions_id_seq OWNED BY public.national_currency_conversions.id;


--
-- Name: news; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.news (
    id integer NOT NULL,
    destination_id integer NOT NULL,
    message text NOT NULL,
    date date DEFAULT now() NOT NULL,
    is_read boolean DEFAULT false
);


--
-- Name: news_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.news_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: news_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.news_id_seq OWNED BY public.news.id;


--
-- Name: node_battles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.node_battles (
    id integer NOT NULL,
    node_id integer,
    attacking_coalition_id integer,
    defending_coalition_id integer,
    status character varying(50) DEFAULT 'ongoing'::character varying NOT NULL,
    started_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    resolves_at timestamp with time zone NOT NULL,
    resolved_at timestamp with time zone
);


--
-- Name: node_battles_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.node_battles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: node_battles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.node_battles_id_seq OWNED BY public.node_battles.id;


--
-- Name: node_yields; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.node_yields (
    id integer NOT NULL,
    node_id integer,
    resource_type character varying(50) NOT NULL,
    amount_per_hour integer NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: node_yields_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.node_yields_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: node_yields_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.node_yields_id_seq OWNED BY public.node_yields.id;


--
-- Name: nodes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nodes (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    type character varying(50) NOT NULL,
    coordinate_x integer NOT NULL,
    coordinate_y integer NOT NULL,
    controlling_coalition_id integer,
    health integer DEFAULT 1000,
    shield_expires_at timestamp with time zone,
    last_resupplied_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    tier integer DEFAULT 1
);


--
-- Name: nodes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.nodes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: nodes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.nodes_id_seq OWNED BY public.nodes.id;


--
-- Name: nuclear_strikes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nuclear_strikes (
    id bigint NOT NULL,
    war_id integer,
    attacker_id integer NOT NULL,
    target_id integer NOT NULL,
    province_id integer NOT NULL,
    province_name text,
    launched_at timestamp with time zone DEFAULT now() NOT NULL,
    recovers_at timestamp with time zone NOT NULL,
    is_retaliation boolean DEFAULT false NOT NULL,
    influence_before bigint DEFAULT 0 NOT NULL,
    influence_cost bigint DEFAULT 0 NOT NULL,
    damage_multiplier numeric(6,4) DEFAULT 1 NOT NULL,
    deaths bigint DEFAULT 0 NOT NULL,
    cities_destroyed integer DEFAULT 0 NOT NULL,
    buildings_destroyed integer DEFAULT 0 NOT NULL,
    happiness_lost integer DEFAULT 0 NOT NULL,
    CONSTRAINT nuclear_strikes_influence_cost_check CHECK ((influence_cost >= 0))
);


--
-- Name: nuclear_strikes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.nuclear_strikes_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: nuclear_strikes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.nuclear_strikes_id_seq OWNED BY public.nuclear_strikes.id;


--
-- Name: offers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.offers (
    offer_id integer NOT NULL,
    type character varying(5) NOT NULL,
    user_id integer NOT NULL,
    resource character varying(50) NOT NULL,
    amount bigint NOT NULL,
    price integer NOT NULL,
    currency_id integer
);


--
-- Name: offers_offer_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.offers_offer_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: offers_offer_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.offers_offer_id_seq OWNED BY public.offers.offer_id;


--
-- Name: patreon_gem_grants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patreon_gem_grants (
    id bigint NOT NULL,
    user_id integer NOT NULL,
    patreon_member_id text NOT NULL,
    tier_title text NOT NULL,
    period text NOT NULL,
    gems_granted bigint NOT NULL,
    granted_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT patreon_gem_grants_gems_granted_check CHECK ((gems_granted > 0))
);


--
-- Name: patreon_gem_grants_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patreon_gem_grants_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patreon_gem_grants_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patreon_gem_grants_id_seq OWNED BY public.patreon_gem_grants.id;


--
-- Name: patreon_tiers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patreon_tiers (
    id bigint NOT NULL,
    title text NOT NULL,
    gems_per_month bigint NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT patreon_tiers_gems_per_month_check CHECK ((gems_per_month > 0))
);


--
-- Name: patreon_tiers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.patreon_tiers_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: patreon_tiers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.patreon_tiers_id_seq OWNED BY public.patreon_tiers.id;


--
-- Name: peace; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.peace (
    id integer NOT NULL,
    author integer NOT NULL,
    demanded_resources text,
    demanded_amount text
);


--
-- Name: peace_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.peace_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: peace_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.peace_id_seq OWNED BY public.peace.id;


--
-- Name: player_reimbursements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.player_reimbursements (
    reimbursement_id text NOT NULL,
    applied_at timestamp with time zone DEFAULT now() NOT NULL,
    total_gold_distributed bigint,
    users_reimbursed integer,
    details jsonb
);


--
-- Name: policies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.policies (
    user_id integer NOT NULL,
    soldiers integer[] DEFAULT '{}'::integer[] NOT NULL,
    education integer[] DEFAULT '{}'::integer[] NOT NULL
);


--
-- Name: policies_user_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.policies_user_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: policies_user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.policies_user_id_seq OWNED BY public.policies.user_id;


--
-- Name: poll_votes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.poll_votes (
    user_id integer NOT NULL,
    poll_name text NOT NULL,
    vote_option text NOT NULL
);


--
-- Name: population_growth_freezes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.population_growth_freezes (
    user_id integer NOT NULL,
    frozen_until timestamp with time zone NOT NULL,
    reason text
);


--
-- Name: proinfra; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.proinfra (
    id integer NOT NULL,
    coal_burners integer DEFAULT 0 NOT NULL,
    oil_burners integer DEFAULT 0 NOT NULL,
    solar_fields integer DEFAULT 0 NOT NULL,
    hydro_dams integer DEFAULT 0 NOT NULL,
    nuclear_reactors integer DEFAULT 0 NOT NULL,
    gas_stations integer DEFAULT 0 NOT NULL,
    general_stores integer DEFAULT 0 NOT NULL,
    farmers_markets integer DEFAULT 0 NOT NULL,
    malls integer DEFAULT 0 NOT NULL,
    banks integer DEFAULT 0 NOT NULL,
    city_parks integer DEFAULT 0 NOT NULL,
    hospitals integer DEFAULT 0 NOT NULL,
    libraries integer DEFAULT 0 NOT NULL,
    universities integer DEFAULT 0 NOT NULL,
    monorails integer DEFAULT 0 NOT NULL,
    army_bases integer DEFAULT 0 NOT NULL,
    aerodomes integer DEFAULT 0 NOT NULL,
    harbours integer DEFAULT 0 NOT NULL,
    admin_buildings integer DEFAULT 0 NOT NULL,
    silos integer DEFAULT 0 NOT NULL,
    farms integer DEFAULT 0 NOT NULL,
    pumpjacks integer DEFAULT 0 NOT NULL,
    coal_mines integer DEFAULT 0 NOT NULL,
    bauxite_mines integer DEFAULT 0 NOT NULL,
    copper_mines integer DEFAULT 0 NOT NULL,
    uranium_mines integer DEFAULT 0 NOT NULL,
    lead_mines integer DEFAULT 0 NOT NULL,
    iron_mines integer DEFAULT 0 NOT NULL,
    lumber_mills integer DEFAULT 0 NOT NULL,
    component_factories integer DEFAULT 0 NOT NULL,
    steel_mills integer DEFAULT 0 NOT NULL,
    ammunition_factories integer DEFAULT 0 NOT NULL,
    aluminium_refineries integer DEFAULT 0 NOT NULL,
    oil_refineries integer DEFAULT 0 NOT NULL,
    logistics_centers integer DEFAULT 0 NOT NULL
);


--
-- Name: province_iron_domes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.province_iron_domes (
    province_id integer NOT NULL,
    quantity integer DEFAULT 0 NOT NULL,
    CONSTRAINT province_iron_domes_quantity_check CHECK ((quantity >= 0))
);


--
-- Name: provinces; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.provinces (
    userid integer NOT NULL,
    id integer NOT NULL,
    provincename character varying(240) NOT NULL,
    citycount integer DEFAULT 1 NOT NULL,
    land integer DEFAULT 1 NOT NULL,
    population bigint DEFAULT 1000000 NOT NULL,
    energy integer DEFAULT 0 NOT NULL,
    happiness integer DEFAULT 0 NOT NULL,
    pollution integer DEFAULT 0 NOT NULL,
    productivity integer DEFAULT 0 NOT NULL,
    consumer_spending integer DEFAULT 0 NOT NULL,
    pop_children bigint DEFAULT 0 NOT NULL,
    pop_working bigint DEFAULT 0 NOT NULL,
    pop_elderly bigint DEFAULT 0 NOT NULL,
    edu_none integer DEFAULT 0 NOT NULL,
    edu_highschool integer DEFAULT 0 NOT NULL,
    edu_college integer DEFAULT 0 NOT NULL,
    image_data text,
    coordinate_x integer,
    coordinate_y integer,
    legacy_max_population bigint DEFAULT 0 NOT NULL,
    is_capital boolean DEFAULT false NOT NULL,
    flag_data text
);


--
-- Name: provinces_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.provinces_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: provinces_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.provinces_id_seq OWNED BY public.provinces.id;


--
-- Name: purchase_audit; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.purchase_audit (
    id integer NOT NULL,
    user_id integer,
    province_id integer,
    unit text,
    units integer,
    gold_before bigint,
    gold_after bigint,
    note text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: purchase_audit_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.purchase_audit_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: purchase_audit_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.purchase_audit_id_seq OWNED BY public.purchase_audit.id;


--
-- Name: referral_active_days; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.referral_active_days (
    referred_user_id integer NOT NULL,
    activity_date date NOT NULL
);


--
-- Name: referral_milestone_payouts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.referral_milestone_payouts (
    id integer NOT NULL,
    referrer_user_id integer NOT NULL,
    referred_user_id integer NOT NULL,
    milestone_days integer NOT NULL,
    paid_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: referral_milestone_payouts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.referral_milestone_payouts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: referral_milestone_payouts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.referral_milestone_payouts_id_seq OWNED BY public.referral_milestone_payouts.id;


--
-- Name: repairs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.repairs (
    id integer NOT NULL,
    user_id integer,
    change_type text,
    details jsonb,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: repairs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.repairs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: repairs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.repairs_id_seq OWNED BY public.repairs.id;


--
-- Name: reparation_tax; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.reparation_tax (
    id integer NOT NULL,
    winner integer NOT NULL,
    loser integer NOT NULL,
    percentage integer NOT NULL,
    until real NOT NULL
);


--
-- Name: reparation_tax_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.reparation_tax_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: reparation_tax_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.reparation_tax_id_seq OWNED BY public.reparation_tax.id;


--
-- Name: requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.requests (
    reqid integer NOT NULL,
    colid integer NOT NULL,
    message character varying(240)
);


--
-- Name: reset_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.reset_codes (
    url_code character varying(120) NOT NULL,
    user_id integer NOT NULL,
    created_at character varying(60) NOT NULL
);


--
-- Name: resource_dictionary; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.resource_dictionary (
    resource_id integer NOT NULL,
    name character varying(50) NOT NULL,
    display_name character varying(100) NOT NULL,
    description text,
    is_production boolean DEFAULT false,
    is_raw boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now(),
    is_active boolean DEFAULT true NOT NULL
);


--
-- Name: resource_dictionary_resource_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.resource_dictionary_resource_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: resource_dictionary_resource_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.resource_dictionary_resource_id_seq OWNED BY public.resource_dictionary.resource_id;


--
-- Name: resources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.resources (
    id integer NOT NULL,
    rations bigint DEFAULT 800 NOT NULL,
    oil bigint DEFAULT 0 NOT NULL,
    coal bigint DEFAULT 0 NOT NULL,
    uranium bigint DEFAULT 0 NOT NULL,
    bauxite bigint DEFAULT 0 NOT NULL,
    iron bigint DEFAULT 0 NOT NULL,
    lead bigint DEFAULT 0 NOT NULL,
    copper bigint DEFAULT 0 NOT NULL,
    lumber bigint DEFAULT 400 NOT NULL,
    components bigint DEFAULT 0 NOT NULL,
    steel bigint DEFAULT 250 NOT NULL,
    consumer_goods bigint DEFAULT 0 NOT NULL,
    aluminium bigint DEFAULT 200 NOT NULL,
    gasoline bigint DEFAULT 0 NOT NULL,
    ammunition bigint DEFAULT 0 NOT NULL
);


--
-- Name: revenue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.revenue (
    id integer NOT NULL,
    user_id integer NOT NULL,
    type character varying(50) NOT NULL,
    name character varying(240) NOT NULL,
    description character varying(240) NOT NULL,
    date character varying(240) NOT NULL,
    resource character varying(50) NOT NULL,
    amount integer DEFAULT 0 NOT NULL
);


--
-- Name: revenue_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.revenue_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: revenue_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.revenue_id_seq OWNED BY public.revenue.id;


--
-- Name: schema_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.schema_migrations (
    name character varying(128) NOT NULL,
    applied_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: signup_attempts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.signup_attempts (
    id integer NOT NULL,
    ip character varying(45),
    fingerprint text,
    email character varying(255),
    attempted_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    successful boolean DEFAULT false,
    ip_address character varying(45),
    attempt_time timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: signup_attempts_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.signup_attempts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: signup_attempts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.signup_attempts_id_seq OWNED BY public.signup_attempts.id;


--
-- Name: site_visits; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.site_visits (
    id bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    day date DEFAULT CURRENT_DATE NOT NULL,
    visitor_hash text NOT NULL,
    user_id integer,
    path text NOT NULL,
    referrer_host text,
    utm_source text,
    utm_medium text,
    utm_campaign text,
    country character(2),
    device text
);


--
-- Name: site_visits_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.site_visits_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: site_visits_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.site_visits_id_seq OWNED BY public.site_visits.id;


--
-- Name: spyinfo; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.spyinfo (
    id integer NOT NULL,
    spyer integer NOT NULL,
    spyee integer NOT NULL,
    soldiers text DEFAULT 'false'::text NOT NULL,
    tanks text DEFAULT 'false'::text NOT NULL,
    artillery text DEFAULT 'false'::text NOT NULL,
    bombers text DEFAULT 'false'::text NOT NULL,
    fighters text DEFAULT 'false'::text NOT NULL,
    apaches text DEFAULT 'false'::text NOT NULL,
    cruisers text DEFAULT 'false'::text NOT NULL,
    destroyers text DEFAULT 'false'::text NOT NULL,
    submarines text DEFAULT 'false'::text NOT NULL,
    spies text DEFAULT 'false'::text NOT NULL,
    icbms text DEFAULT 'false'::text NOT NULL,
    nukes text DEFAULT 'false'::text NOT NULL,
    rations text DEFAULT 'false'::text NOT NULL,
    bauxite text DEFAULT 'false'::text NOT NULL,
    uranium text DEFAULT 'false'::text NOT NULL,
    iron text DEFAULT 'false'::text NOT NULL,
    coal text DEFAULT 'false'::text NOT NULL,
    oil text DEFAULT 'false'::text NOT NULL,
    lead text DEFAULT 'false'::text NOT NULL,
    copper text DEFAULT 'false'::text NOT NULL,
    lumber text DEFAULT 'false'::text NOT NULL,
    components text DEFAULT 'false'::text NOT NULL,
    steel text DEFAULT 'false'::text NOT NULL,
    aluminium text DEFAULT 'false'::text NOT NULL,
    gasoline text DEFAULT 'false'::text NOT NULL,
    ammunition text DEFAULT 'false'::text NOT NULL,
    consumer_goods text DEFAULT 'false'::text NOT NULL,
    money text DEFAULT 'false'::text NOT NULL,
    defense text DEFAULT 'false'::text NOT NULL,
    date integer NOT NULL,
    spy_type text,
    intercepted boolean DEFAULT false NOT NULL,
    silver bigint DEFAULT 0,
    diamonds bigint DEFAULT 0,
    bullion bigint DEFAULT 0,
    sam_batteries bigint DEFAULT 0,
    iron_domes bigint
);


--
-- Name: spyinfo_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.spyinfo_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: spyinfo_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.spyinfo_id_seq OWNED BY public.spyinfo.id;


--
-- Name: stats; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.stats (
    id integer NOT NULL,
    location character varying(100) NOT NULL,
    gold bigint DEFAULT 80000000 NOT NULL,
    manpower integer DEFAULT 0 NOT NULL,
    default_defense character varying(200) DEFAULT 'soldiers,tanks,artillery'::character varying NOT NULL,
    x integer DEFAULT 0 NOT NULL,
    y integer DEFAULT 0 NOT NULL,
    tutorial_chapters_claimed integer[] DEFAULT '{}'::integer[],
    tutorial_graduated_at timestamp with time zone,
    tutorial_step integer DEFAULT 0,
    gems bigint DEFAULT 0 NOT NULL,
    equipped_background_cosmetic_id bigint,
    equipped_name_color_cosmetic_id bigint,
    equipped_badge_cosmetic_id bigint,
    equipped_title_cosmetic_id bigint,
    equipped_country_border_cosmetic_id bigint,
    national_currency_balance numeric(18,2) DEFAULT 0 NOT NULL,
    CONSTRAINT stats_gems_check CHECK ((gems >= 0)),
    CONSTRAINT stats_gold_check CHECK ((gold >= 0))
);


--
-- Name: task_cursors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_cursors (
    task_name text NOT NULL,
    last_id bigint
);


--
-- Name: task_metrics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_metrics (
    id integer NOT NULL,
    task_name text,
    duration_seconds double precision,
    measured_at timestamp with time zone DEFAULT now()
);


--
-- Name: task_metrics_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.task_metrics_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: task_metrics_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.task_metrics_id_seq OWNED BY public.task_metrics.id;


--
-- Name: task_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_runs (
    task_name text NOT NULL,
    last_run timestamp with time zone
);


--
-- Name: tech_dictionary; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tech_dictionary (
    tech_id integer NOT NULL,
    name character varying(100) NOT NULL,
    display_name character varying(100) NOT NULL,
    category character varying(50) NOT NULL,
    research_cost bigint NOT NULL,
    prerequisite_tech_id integer,
    effect_type character varying(50),
    effect_value numeric(10,2),
    description text,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    CONSTRAINT tech_dictionary_research_cost_check CHECK ((research_cost > 0)),
    CONSTRAINT tech_valid_category CHECK (((category)::text = ANY ((ARRAY['agriculture'::character varying, 'industry'::character varying, 'military'::character varying, 'science'::character varying, 'infrastructure'::character varying, 'diplomacy'::character varying])::text[])))
);


--
-- Name: tech_dictionary_tech_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tech_dictionary_tech_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tech_dictionary_tech_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tech_dictionary_tech_id_seq OWNED BY public.tech_dictionary.tech_id;


--
-- Name: totp_backup_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.totp_backup_codes (
    id integer NOT NULL,
    user_id integer NOT NULL,
    code_hash text NOT NULL,
    used_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: totp_backup_codes_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.totp_backup_codes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: totp_backup_codes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.totp_backup_codes_id_seq OWNED BY public.totp_backup_codes.id;


--
-- Name: trade_agreements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trade_agreements (
    id integer NOT NULL,
    proposer_id integer NOT NULL,
    proposer_resource text NOT NULL,
    proposer_amount integer NOT NULL,
    receiver_id integer NOT NULL,
    receiver_resource text NOT NULL,
    receiver_amount integer NOT NULL,
    interval_hours integer DEFAULT 24 NOT NULL,
    next_execution timestamp with time zone,
    last_execution timestamp with time zone,
    max_executions integer,
    execution_count integer DEFAULT 0,
    status text DEFAULT 'pending'::text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    message text
);


--
-- Name: trade_agreements_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.trade_agreements_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: trade_agreements_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.trade_agreements_id_seq OWNED BY public.trade_agreements.id;


--
-- Name: trade_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trade_events (
    id integer NOT NULL,
    offer_id text,
    offerer integer,
    offeree integer,
    resource text,
    amount integer,
    price integer,
    total integer,
    trade_type text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: trade_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.trade_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: trade_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.trade_events_id_seq OWNED BY public.trade_events.id;


--
-- Name: trades; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.trades (
    offer_id integer NOT NULL,
    type character varying(5) NOT NULL,
    offerer integer NOT NULL,
    offeree integer NOT NULL,
    resource character varying(50) NOT NULL,
    amount integer NOT NULL,
    price integer NOT NULL,
    currency_id integer
);


--
-- Name: trades_offer_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.trades_offer_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: trades_offer_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.trades_offer_id_seq OWNED BY public.trades.offer_id;


--
-- Name: treaties; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.treaties (
    id integer NOT NULL,
    col1_id integer NOT NULL,
    col2_id integer NOT NULL,
    treaty_name character varying(100) NOT NULL,
    treaty_description character varying(5000) NOT NULL,
    status character varying(20) DEFAULT 'Pending'::character varying
);


--
-- Name: treaties_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.treaties_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: treaties_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.treaties_id_seq OWNED BY public.treaties.id;


--
-- Name: unit_dictionary; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.unit_dictionary (
    unit_id integer NOT NULL,
    name character varying(100) NOT NULL,
    display_name character varying(100) NOT NULL,
    combat_type character varying(50) NOT NULL,
    base_attack numeric(10,2) DEFAULT 0 NOT NULL,
    base_defense numeric(10,2) DEFAULT 0 NOT NULL,
    maintenance_cost_resource_id integer,
    maintenance_cost_amount bigint DEFAULT 0,
    manpower_required bigint DEFAULT 0,
    production_cost_rations bigint DEFAULT 0,
    production_cost_components bigint DEFAULT 0,
    production_cost_steel bigint DEFAULT 0,
    production_cost_fuel bigint DEFAULT 0,
    description text,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    production_cost_aluminium integer DEFAULT 0,
    production_cost_uranium bigint DEFAULT 0,
    CONSTRAINT unit_valid_combat_type CHECK (((combat_type)::text = ANY ((ARRAY['infantry'::character varying, 'vehicle'::character varying, 'naval'::character varying, 'espionage'::character varying, 'strategic'::character varying])::text[])))
);


--
-- Name: unit_dictionary_unit_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.unit_dictionary_unit_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: unit_dictionary_unit_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.unit_dictionary_unit_id_seq OWNED BY public.unit_dictionary.unit_id;


--
-- Name: upgrades; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.upgrades (
    user_id integer NOT NULL,
    betterengineering integer DEFAULT 0,
    cheapermaterials integer DEFAULT 0,
    onlineshopping integer DEFAULT 0,
    governmentregulation integer DEFAULT 0,
    nationalhealthinstitution integer DEFAULT 0,
    highspeedrail integer DEFAULT 0,
    advancedmachinery integer DEFAULT 0,
    strongerexplosives integer DEFAULT 0,
    widespreadpropaganda integer DEFAULT 0,
    increasedfunding integer DEFAULT 0,
    automationintegration integer DEFAULT 0,
    largerforges integer DEFAULT 0,
    lootingteams integer DEFAULT 0,
    organizedsupplylines integer DEFAULT 0,
    largestorehouses integer DEFAULT 0,
    ballisticmissilesilo integer DEFAULT 0,
    icbmsilo integer DEFAULT 0,
    nucleartestingfacility integer DEFAULT 0
);


--
-- Name: user_achievements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_achievements (
    user_id integer NOT NULL,
    key character varying(64) NOT NULL,
    unlocked_at timestamp with time zone DEFAULT (now() AT TIME ZONE 'UTC'::text) NOT NULL
);


--
-- Name: user_active_days; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_active_days (
    user_id integer NOT NULL,
    day date NOT NULL,
    source text DEFAULT 'tracked'::text NOT NULL
);


--
-- Name: user_buildings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_buildings (
    user_id integer NOT NULL,
    building_id integer NOT NULL,
    quantity integer DEFAULT 0 NOT NULL,
    last_upgraded timestamp with time zone DEFAULT now(),
    province_id integer NOT NULL,
    CONSTRAINT user_buildings_quantity_check CHECK ((quantity >= 0))
);


--
-- Name: user_cosmetics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_cosmetics (
    id bigint NOT NULL,
    user_id integer NOT NULL,
    cosmetic_id bigint NOT NULL,
    purchased_at timestamp with time zone DEFAULT now() NOT NULL,
    gems_spent bigint NOT NULL
);


--
-- Name: user_cosmetics_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_cosmetics_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_cosmetics_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_cosmetics_id_seq OWNED BY public.user_cosmetics.id;


--
-- Name: user_economy; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_economy (
    user_id integer NOT NULL,
    resource_id integer NOT NULL,
    quantity bigint DEFAULT 0 NOT NULL,
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT user_economy_quantity_check CHECK ((quantity >= 0))
);


--
-- Name: user_loans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_loans (
    id integer NOT NULL,
    user_id integer NOT NULL,
    principal numeric NOT NULL,
    balance numeric NOT NULL,
    interest_rate numeric NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    taken_at timestamp with time zone DEFAULT now() NOT NULL,
    repaid_at timestamp with time zone,
    cap_at_take bigint
);


--
-- Name: user_loans_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_loans_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_loans_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_loans_id_seq OWNED BY public.user_loans.id;


--
-- Name: user_military; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_military (
    user_id integer NOT NULL,
    unit_id integer NOT NULL,
    quantity bigint DEFAULT 0 NOT NULL,
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT user_military_quantity_check CHECK ((quantity >= 0))
);


--
-- Name: user_tech; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_tech (
    user_id integer NOT NULL,
    tech_id integer NOT NULL,
    is_unlocked boolean DEFAULT false NOT NULL,
    research_progress numeric(5,2) DEFAULT 0,
    unlocked_at timestamp with time zone,
    CONSTRAINT user_tech_research_progress_check CHECK (((research_progress >= (0)::numeric) AND (research_progress <= (100)::numeric)))
);


--
-- Name: user_unit_stockpile; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_unit_stockpile (
    user_id integer NOT NULL,
    unit_id integer NOT NULL,
    quantity bigint DEFAULT 0 NOT NULL,
    updated_at timestamp with time zone DEFAULT now(),
    CONSTRAINT user_unit_stockpile_quantity_check CHECK ((quantity >= 0))
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username character varying(60) NOT NULL,
    email character varying(100) NOT NULL,
    date character varying(10) NOT NULL,
    hash character varying(255) NOT NULL,
    description text,
    flag character varying(30),
    bg_flag character varying(30),
    auth_type character varying(50),
    motto character varying(100) DEFAULT NULL::character varying,
    flag_data text,
    is_verified boolean DEFAULT false,
    verification_token text,
    token_created_at timestamp with time zone,
    verification_email_failed_at timestamp without time zone,
    last_active timestamp with time zone,
    join_number integer,
    discord_id character varying(255),
    recovery_key character varying(255),
    referral_code character varying(12),
    referred_by_user_id integer,
    reset_count integer DEFAULT 0 NOT NULL,
    session_epoch integer DEFAULT 0 NOT NULL,
    totp_secret_encrypted text,
    totp_enabled boolean DEFAULT false NOT NULL,
    totp_enrolled_at timestamp with time zone,
    leader_name character varying(60),
    currency_name character varying(40),
    ruling_party character varying(60),
    allow_coalition_builds boolean DEFAULT false NOT NULL,
    public_province_info boolean DEFAULT false NOT NULL,
    coalition_builds_choice_set boolean DEFAULT false NOT NULL,
    signup_referrer_host text,
    signup_landing_path text,
    signup_utm_source text,
    signup_utm_medium text,
    signup_utm_campaign text,
    signup_country character(2),
    signup_device text,
    signup_heard_from text,
    signup_channel_source text
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: war_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.war_events (
    id integer NOT NULL,
    war_id integer,
    winner integer,
    loser integer,
    winner_losses text,
    loser_losses text,
    morale_column text,
    morale_delta integer,
    new_morale integer,
    win_label text,
    concluded boolean,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: war_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.war_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: war_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.war_events_id_seq OWNED BY public.war_events.id;


--
-- Name: wars; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wars (
    id integer NOT NULL,
    attacker integer NOT NULL,
    defender integer NOT NULL,
    war_type text NOT NULL,
    agressor_message character varying(240) NOT NULL,
    peace_date real,
    start_date real NOT NULL,
    attacker_supplies integer DEFAULT 200,
    defender_supplies integer DEFAULT 200,
    last_visited real NOT NULL,
    attacker_morale integer DEFAULT 100,
    defender_morale integer DEFAULT 100,
    peace_offer_id integer,
    aggressor_message character varying(240),
    status character varying(20) DEFAULT 'active'::character varying,
    winner_id integer,
    last_attack_resolved_at double precision
);


--
-- Name: wars_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.wars_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: wars_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.wars_id_seq OWNED BY public.wars.id;


--
-- Name: wars_normalized; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.wars_normalized (
    war_id integer NOT NULL,
    attacker_id integer NOT NULL,
    defender_id integer NOT NULL,
    war_type character varying(50) NOT NULL,
    aggressor_message character varying(240),
    peace_date timestamp with time zone,
    start_date timestamp with time zone DEFAULT now() NOT NULL,
    attacker_supplies integer DEFAULT 200,
    defender_supplies integer DEFAULT 200,
    last_visited timestamp with time zone DEFAULT now() NOT NULL,
    attacker_morale integer DEFAULT 100,
    defender_morale integer DEFAULT 100,
    peace_offer_id integer,
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    winner_id integer,
    CONSTRAINT wars_different_parties CHECK ((attacker_id <> defender_id)),
    CONSTRAINT wars_normalized_attacker_morale_check CHECK (((attacker_morale >= 0) AND (attacker_morale <= 100))),
    CONSTRAINT wars_normalized_attacker_supplies_check CHECK ((attacker_supplies >= 0)),
    CONSTRAINT wars_normalized_defender_morale_check CHECK (((defender_morale >= 0) AND (defender_morale <= 100))),
    CONSTRAINT wars_normalized_defender_supplies_check CHECK ((defender_supplies >= 0)),
    CONSTRAINT wars_valid_status CHECK (((status)::text = ANY ((ARRAY['active'::character varying, 'ended'::character varying, 'peace'::character varying, 'surrender'::character varying])::text[])))
);


--
-- Name: wars_normalized_war_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.wars_normalized_war_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: wars_normalized_war_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.wars_normalized_war_id_seq OWNED BY public.wars_normalized.war_id;


--
-- Name: world_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.world_events (
    id integer NOT NULL,
    event_type character varying(30) NOT NULL,
    message text NOT NULL,
    actor_id integer,
    target_id integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: world_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.world_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: world_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.world_events_id_seq OWNED BY public.world_events.id;


--
-- Name: admin_actions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_actions ALTER COLUMN id SET DEFAULT nextval('public.admin_actions_id_seq'::regclass);


--
-- Name: advertisements id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.advertisements ALTER COLUMN id SET DEFAULT nextval('public.advertisements_id_seq'::regclass);


--
-- Name: assembly_effects id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assembly_effects ALTER COLUMN id SET DEFAULT nextval('public.assembly_effects_id_seq'::regclass);


--
-- Name: assembly_proposals id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assembly_proposals ALTER COLUMN id SET DEFAULT nextval('public.assembly_proposals_id_seq'::regclass);


--
-- Name: assembly_votes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assembly_votes ALTER COLUMN id SET DEFAULT nextval('public.assembly_votes_id_seq'::regclass);


--
-- Name: bmc_gem_purchases id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bmc_gem_purchases ALTER COLUMN id SET DEFAULT nextval('public.bmc_gem_purchases_id_seq'::regclass);


--
-- Name: bonds id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bonds ALTER COLUMN id SET DEFAULT nextval('public.bonds_id_seq'::regclass);


--
-- Name: bounties id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bounties ALTER COLUMN id SET DEFAULT nextval('public.bounties_id_seq'::regclass);


--
-- Name: building_dictionary building_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.building_dictionary ALTER COLUMN building_id SET DEFAULT nextval('public.building_dictionary_building_id_seq'::regclass);


--
-- Name: coalition_invites id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalition_invites ALTER COLUMN id SET DEFAULT nextval('public.coalition_invites_id_seq'::regclass);


--
-- Name: coalition_messages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalition_messages ALTER COLUMN id SET DEFAULT nextval('public.coalition_messages_id_seq'::regclass);


--
-- Name: coalitions_normalized coalition_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalitions_normalized ALTER COLUMN coalition_id SET DEFAULT nextval('public.coalitions_normalized_coalition_id_seq'::regclass);


--
-- Name: col_applications id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.col_applications ALTER COLUMN id SET DEFAULT nextval('public.col_applications_id_seq'::regclass);


--
-- Name: col_bank_recurring_trade_runs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.col_bank_recurring_trade_runs ALTER COLUMN id SET DEFAULT nextval('public.col_bank_recurring_trade_runs_id_seq'::regclass);


--
-- Name: col_bank_recurring_trades id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.col_bank_recurring_trades ALTER COLUMN id SET DEFAULT nextval('public.col_bank_recurring_trades_id_seq'::regclass);


--
-- Name: col_bank_trades id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.col_bank_trades ALTER COLUMN id SET DEFAULT nextval('public.col_bank_trades_id_seq'::regclass);


--
-- Name: col_bank_transactions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.col_bank_transactions ALTER COLUMN id SET DEFAULT nextval('public.col_bank_transactions_id_seq'::regclass);


--
-- Name: colbanksrequests id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.colbanksrequests ALTER COLUMN id SET DEFAULT nextval('public.colbanksrequests_id_seq'::regclass);


--
-- Name: colnames id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.colnames ALTER COLUMN id SET DEFAULT nextval('public.colnames_id_seq'::regclass);


--
-- Name: cosmetics id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cosmetics ALTER COLUMN id SET DEFAULT nextval('public.cosmetics_id_seq'::regclass);


--
-- Name: currency_market_offers offer_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.currency_market_offers ALTER COLUMN offer_id SET DEFAULT nextval('public.currency_market_offers_offer_id_seq'::regclass);


--
-- Name: currency_market_trades id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.currency_market_trades ALTER COLUMN id SET DEFAULT nextval('public.currency_market_trades_id_seq'::regclass);


--
-- Name: currency_unions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.currency_unions ALTER COLUMN id SET DEFAULT nextval('public.currency_unions_id_seq'::regclass);


--
-- Name: devlog_entries id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.devlog_entries ALTER COLUMN id SET DEFAULT nextval('public.devlog_entries_id_seq'::regclass);


--
-- Name: direct_messages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.direct_messages ALTER COLUMN id SET DEFAULT nextval('public.direct_messages_id_seq'::regclass);


--
-- Name: discord_custom_commands id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_custom_commands ALTER COLUMN id SET DEFAULT nextval('public.discord_custom_commands_id_seq'::regclass);


--
-- Name: discord_giveaways id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_giveaways ALTER COLUMN id SET DEFAULT nextval('public.discord_giveaways_id_seq'::regclass);


--
-- Name: discord_mod_cases id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_mod_cases ALTER COLUMN id SET DEFAULT nextval('public.discord_mod_cases_id_seq'::regclass);


--
-- Name: discord_suggestions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_suggestions ALTER COLUMN id SET DEFAULT nextval('public.discord_suggestions_id_seq'::regclass);


--
-- Name: discord_tickets id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_tickets ALTER COLUMN id SET DEFAULT nextval('public.discord_tickets_id_seq'::regclass);


--
-- Name: forum_replies id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.forum_replies ALTER COLUMN id SET DEFAULT nextval('public.forum_replies_id_seq'::regclass);


--
-- Name: forum_threads id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.forum_threads ALTER COLUMN id SET DEFAULT nextval('public.forum_threads_id_seq'::regclass);


--
-- Name: game_economy_snapshots id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.game_economy_snapshots ALTER COLUMN id SET DEFAULT nextval('public.game_economy_snapshots_id_seq'::regclass);


--
-- Name: game_tick_logs tick_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.game_tick_logs ALTER COLUMN tick_id SET DEFAULT nextval('public.game_tick_logs_tick_id_seq'::regclass);


--
-- Name: gem_packages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gem_packages ALTER COLUMN id SET DEFAULT nextval('public.gem_packages_id_seq'::regclass);


--
-- Name: gem_purchases id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gem_purchases ALTER COLUMN id SET DEFAULT nextval('public.gem_purchases_id_seq'::regclass);


--
-- Name: global_chat_messages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.global_chat_messages ALTER COLUMN id SET DEFAULT nextval('public.global_chat_messages_id_seq'::regclass);


--
-- Name: global_market market_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.global_market ALTER COLUMN market_id SET DEFAULT nextval('public.global_market_market_id_seq'::regclass);


--
-- Name: identity_diagnostic_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_diagnostic_log ALTER COLUMN id SET DEFAULT nextval('public.identity_diagnostic_log_id_seq'::regclass);


--
-- Name: interactive_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interactive_events ALTER COLUMN id SET DEFAULT nextval('public.interactive_events_id_seq'::regclass);


--
-- Name: login_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.login_events ALTER COLUMN id SET DEFAULT nextval('public.login_events_id_seq'::regclass);


--
-- Name: login_verifications id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.login_verifications ALTER COLUMN id SET DEFAULT nextval('public.login_verifications_id_seq'::regclass);


--
-- Name: map_combat_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.map_combat_log ALTER COLUMN id SET DEFAULT nextval('public.map_combat_log_id_seq'::regclass);


--
-- Name: map_objects id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.map_objects ALTER COLUMN id SET DEFAULT nextval('public.map_objects_id_seq'::regclass);


--
-- Name: map_unit_deployments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.map_unit_deployments ALTER COLUMN id SET DEFAULT nextval('public.map_unit_deployments_id_seq'::regclass);


--
-- Name: marches id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.marches ALTER COLUMN id SET DEFAULT nextval('public.marches_id_seq'::regclass);


--
-- Name: market_auto_order_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_auto_order_log ALTER COLUMN id SET DEFAULT nextval('public.market_auto_order_log_id_seq'::regclass);


--
-- Name: market_auto_orders id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_auto_orders ALTER COLUMN id SET DEFAULT nextval('public.market_auto_orders_id_seq'::regclass);


--
-- Name: market_fills id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_fills ALTER COLUMN id SET DEFAULT nextval('public.market_fills_id_seq'::regclass);


--
-- Name: nation_revenue_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nation_revenue_history ALTER COLUMN id SET DEFAULT nextval('public.nation_revenue_history_id_seq'::regclass);


--
-- Name: nation_treaties id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nation_treaties ALTER COLUMN id SET DEFAULT nextval('public.nation_treaties_id_seq'::regclass);


--
-- Name: national_currency_conversions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.national_currency_conversions ALTER COLUMN id SET DEFAULT nextval('public.national_currency_conversions_id_seq'::regclass);


--
-- Name: news id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.news ALTER COLUMN id SET DEFAULT nextval('public.news_id_seq'::regclass);


--
-- Name: node_battles id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_battles ALTER COLUMN id SET DEFAULT nextval('public.node_battles_id_seq'::regclass);


--
-- Name: node_yields id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_yields ALTER COLUMN id SET DEFAULT nextval('public.node_yields_id_seq'::regclass);


--
-- Name: nodes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nodes ALTER COLUMN id SET DEFAULT nextval('public.nodes_id_seq'::regclass);


--
-- Name: nuclear_strikes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nuclear_strikes ALTER COLUMN id SET DEFAULT nextval('public.nuclear_strikes_id_seq'::regclass);


--
-- Name: offers offer_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offers ALTER COLUMN offer_id SET DEFAULT nextval('public.offers_offer_id_seq'::regclass);


--
-- Name: patreon_gem_grants id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patreon_gem_grants ALTER COLUMN id SET DEFAULT nextval('public.patreon_gem_grants_id_seq'::regclass);


--
-- Name: patreon_tiers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patreon_tiers ALTER COLUMN id SET DEFAULT nextval('public.patreon_tiers_id_seq'::regclass);


--
-- Name: peace id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.peace ALTER COLUMN id SET DEFAULT nextval('public.peace_id_seq'::regclass);


--
-- Name: provinces id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provinces ALTER COLUMN id SET DEFAULT nextval('public.provinces_id_seq'::regclass);


--
-- Name: purchase_audit id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_audit ALTER COLUMN id SET DEFAULT nextval('public.purchase_audit_id_seq'::regclass);


--
-- Name: referral_milestone_payouts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_milestone_payouts ALTER COLUMN id SET DEFAULT nextval('public.referral_milestone_payouts_id_seq'::regclass);


--
-- Name: repairs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.repairs ALTER COLUMN id SET DEFAULT nextval('public.repairs_id_seq'::regclass);


--
-- Name: reparation_tax id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reparation_tax ALTER COLUMN id SET DEFAULT nextval('public.reparation_tax_id_seq'::regclass);


--
-- Name: resource_dictionary resource_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_dictionary ALTER COLUMN resource_id SET DEFAULT nextval('public.resource_dictionary_resource_id_seq'::regclass);


--
-- Name: revenue id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.revenue ALTER COLUMN id SET DEFAULT nextval('public.revenue_id_seq'::regclass);


--
-- Name: signup_attempts id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signup_attempts ALTER COLUMN id SET DEFAULT nextval('public.signup_attempts_id_seq'::regclass);


--
-- Name: site_visits id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.site_visits ALTER COLUMN id SET DEFAULT nextval('public.site_visits_id_seq'::regclass);


--
-- Name: spyinfo id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.spyinfo ALTER COLUMN id SET DEFAULT nextval('public.spyinfo_id_seq'::regclass);


--
-- Name: task_metrics id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_metrics ALTER COLUMN id SET DEFAULT nextval('public.task_metrics_id_seq'::regclass);


--
-- Name: tech_dictionary tech_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tech_dictionary ALTER COLUMN tech_id SET DEFAULT nextval('public.tech_dictionary_tech_id_seq'::regclass);


--
-- Name: totp_backup_codes id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.totp_backup_codes ALTER COLUMN id SET DEFAULT nextval('public.totp_backup_codes_id_seq'::regclass);


--
-- Name: trade_agreements id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trade_agreements ALTER COLUMN id SET DEFAULT nextval('public.trade_agreements_id_seq'::regclass);


--
-- Name: trade_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trade_events ALTER COLUMN id SET DEFAULT nextval('public.trade_events_id_seq'::regclass);


--
-- Name: trades offer_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trades ALTER COLUMN offer_id SET DEFAULT nextval('public.trades_offer_id_seq'::regclass);


--
-- Name: treaties id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treaties ALTER COLUMN id SET DEFAULT nextval('public.treaties_id_seq'::regclass);


--
-- Name: unit_dictionary unit_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.unit_dictionary ALTER COLUMN unit_id SET DEFAULT nextval('public.unit_dictionary_unit_id_seq'::regclass);


--
-- Name: user_cosmetics id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_cosmetics ALTER COLUMN id SET DEFAULT nextval('public.user_cosmetics_id_seq'::regclass);


--
-- Name: user_loans id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_loans ALTER COLUMN id SET DEFAULT nextval('public.user_loans_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: war_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.war_events ALTER COLUMN id SET DEFAULT nextval('public.war_events_id_seq'::regclass);


--
-- Name: wars id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wars ALTER COLUMN id SET DEFAULT nextval('public.wars_id_seq'::regclass);


--
-- Name: wars_normalized war_id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wars_normalized ALTER COLUMN war_id SET DEFAULT nextval('public.wars_normalized_war_id_seq'::regclass);


--
-- Name: world_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.world_events ALTER COLUMN id SET DEFAULT nextval('public.world_events_id_seq'::regclass);


--
-- Name: achievements achievements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.achievements
    ADD CONSTRAINT achievements_pkey PRIMARY KEY (key);


--
-- Name: admin_actions admin_actions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_actions
    ADD CONSTRAINT admin_actions_pkey PRIMARY KEY (id);


--
-- Name: admin_user_controls admin_user_controls_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_user_controls
    ADD CONSTRAINT admin_user_controls_pkey PRIMARY KEY (user_id);


--
-- Name: advertisements advertisements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.advertisements
    ADD CONSTRAINT advertisements_pkey PRIMARY KEY (id);


--
-- Name: assembly_effects assembly_effects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assembly_effects
    ADD CONSTRAINT assembly_effects_pkey PRIMARY KEY (id);


--
-- Name: assembly_proposals assembly_proposals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assembly_proposals
    ADD CONSTRAINT assembly_proposals_pkey PRIMARY KEY (id);


--
-- Name: assembly_votes assembly_votes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assembly_votes
    ADD CONSTRAINT assembly_votes_pkey PRIMARY KEY (id);


--
-- Name: assembly_votes assembly_votes_proposal_id_voter_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assembly_votes
    ADD CONSTRAINT assembly_votes_proposal_id_voter_id_key UNIQUE (proposal_id, voter_id);


--
-- Name: bmc_gem_purchases bmc_gem_purchases_bmc_transaction_id_bmc_extra_line_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bmc_gem_purchases
    ADD CONSTRAINT bmc_gem_purchases_bmc_transaction_id_bmc_extra_line_id_key UNIQUE (bmc_transaction_id, bmc_extra_line_id);


--
-- Name: bmc_gem_purchases bmc_gem_purchases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bmc_gem_purchases
    ADD CONSTRAINT bmc_gem_purchases_pkey PRIMARY KEY (id);


--
-- Name: bonds bonds_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bonds
    ADD CONSTRAINT bonds_pkey PRIMARY KEY (id);


--
-- Name: bounties bounties_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bounties
    ADD CONSTRAINT bounties_pkey PRIMARY KEY (id);


--
-- Name: building_dictionary building_dictionary_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.building_dictionary
    ADD CONSTRAINT building_dictionary_name_key UNIQUE (name);


--
-- Name: building_dictionary building_dictionary_name_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.building_dictionary
    ADD CONSTRAINT building_dictionary_name_unique UNIQUE (name);


--
-- Name: building_dictionary building_dictionary_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.building_dictionary
    ADD CONSTRAINT building_dictionary_pkey PRIMARY KEY (building_id);


--
-- Name: coalition_bond_insurance coalition_bond_insurance_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalition_bond_insurance
    ADD CONSTRAINT coalition_bond_insurance_pkey PRIMARY KEY (coalition_id, user_id);


--
-- Name: coalition_invites coalition_invites_coalition_id_invited_user_id_status_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalition_invites
    ADD CONSTRAINT coalition_invites_coalition_id_invited_user_id_status_key UNIQUE (coalition_id, invited_user_id, status);


--
-- Name: coalition_invites coalition_invites_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalition_invites
    ADD CONSTRAINT coalition_invites_pkey PRIMARY KEY (id);


--
-- Name: coalition_members coalition_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalition_members
    ADD CONSTRAINT coalition_members_pkey PRIMARY KEY (user_id, coalition_id);


--
-- Name: coalition_messages coalition_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalition_messages
    ADD CONSTRAINT coalition_messages_pkey PRIMARY KEY (id);


--
-- Name: coalitions_normalized coalitions_normalized_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalitions_normalized
    ADD CONSTRAINT coalitions_normalized_name_key UNIQUE (name);


--
-- Name: coalitions_normalized coalitions_normalized_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalitions_normalized
    ADD CONSTRAINT coalitions_normalized_pkey PRIMARY KEY (coalition_id);


--
-- Name: coalitions_legacy coalitions_userid_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalitions_legacy
    ADD CONSTRAINT coalitions_userid_key UNIQUE (userid);


--
-- Name: col_applications col_applications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.col_applications
    ADD CONSTRAINT col_applications_pkey PRIMARY KEY (id);


--
-- Name: col_bank_contributions col_bank_contributions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.col_bank_contributions
    ADD CONSTRAINT col_bank_contributions_pkey PRIMARY KEY (coalition_id, user_id, resource);


--
-- Name: col_bank_recurring_trade_runs col_bank_recurring_trade_runs_once; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.col_bank_recurring_trade_runs
    ADD CONSTRAINT col_bank_recurring_trade_runs_once UNIQUE (recurring_trade_id, scheduled_for);


--
-- Name: col_bank_recurring_trade_runs col_bank_recurring_trade_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.col_bank_recurring_trade_runs
    ADD CONSTRAINT col_bank_recurring_trade_runs_pkey PRIMARY KEY (id);


--
-- Name: col_bank_recurring_trades col_bank_recurring_trades_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.col_bank_recurring_trades
    ADD CONSTRAINT col_bank_recurring_trades_pkey PRIMARY KEY (id);


--
-- Name: col_bank_trades col_bank_trades_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.col_bank_trades
    ADD CONSTRAINT col_bank_trades_pkey PRIMARY KEY (id);


--
-- Name: col_bank_transactions col_bank_transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.col_bank_transactions
    ADD CONSTRAINT col_bank_transactions_pkey PRIMARY KEY (id);


--
-- Name: col_role_names col_role_names_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.col_role_names
    ADD CONSTRAINT col_role_names_pkey PRIMARY KEY (coalition_id, role);


--
-- Name: colbanks colbanks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.colbanks
    ADD CONSTRAINT colbanks_pkey PRIMARY KEY (colid);


--
-- Name: colbanksrequests colbanksrequests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.colbanksrequests
    ADD CONSTRAINT colbanksrequests_pkey PRIMARY KEY (id);


--
-- Name: colnames colnames_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.colnames
    ADD CONSTRAINT colnames_name_key UNIQUE (name);


--
-- Name: colnames colnames_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.colnames
    ADD CONSTRAINT colnames_pkey PRIMARY KEY (id);


--
-- Name: cosmetics cosmetics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cosmetics
    ADD CONSTRAINT cosmetics_pkey PRIMARY KEY (id);


--
-- Name: cosmetics cosmetics_slug_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.cosmetics
    ADD CONSTRAINT cosmetics_slug_key UNIQUE (slug);


--
-- Name: currency_holdings currency_holdings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.currency_holdings
    ADD CONSTRAINT currency_holdings_pkey PRIMARY KEY (user_id, issuer_id);


--
-- Name: currency_market_offers currency_market_offers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.currency_market_offers
    ADD CONSTRAINT currency_market_offers_pkey PRIMARY KEY (offer_id);


--
-- Name: currency_market_trades currency_market_trades_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.currency_market_trades
    ADD CONSTRAINT currency_market_trades_pkey PRIMARY KEY (id);


--
-- Name: currency_union_applications currency_union_applications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.currency_union_applications
    ADD CONSTRAINT currency_union_applications_pkey PRIMARY KEY (union_id, user_id);


--
-- Name: currency_union_members currency_union_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.currency_union_members
    ADD CONSTRAINT currency_union_members_pkey PRIMARY KEY (user_id);


--
-- Name: currency_unions currency_unions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.currency_unions
    ADD CONSTRAINT currency_unions_pkey PRIMARY KEY (id);


--
-- Name: devlog_entries devlog_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.devlog_entries
    ADD CONSTRAINT devlog_entries_pkey PRIMARY KEY (id);


--
-- Name: direct_messages direct_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.direct_messages
    ADD CONSTRAINT direct_messages_pkey PRIMARY KEY (id);


--
-- Name: discord_bad_words discord_bad_words_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_bad_words
    ADD CONSTRAINT discord_bad_words_pkey PRIMARY KEY (guild_id, word);


--
-- Name: discord_custom_commands discord_custom_commands_guild_id_trigger_word_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_custom_commands
    ADD CONSTRAINT discord_custom_commands_guild_id_trigger_word_key UNIQUE (guild_id, trigger_word);


--
-- Name: discord_custom_commands discord_custom_commands_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_custom_commands
    ADD CONSTRAINT discord_custom_commands_pkey PRIMARY KEY (id);


--
-- Name: discord_giveaways discord_giveaways_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_giveaways
    ADD CONSTRAINT discord_giveaways_pkey PRIMARY KEY (id);


--
-- Name: discord_guild_settings discord_guild_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_guild_settings
    ADD CONSTRAINT discord_guild_settings_pkey PRIMARY KEY (guild_id);


--
-- Name: discord_level_config discord_level_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_level_config
    ADD CONSTRAINT discord_level_config_pkey PRIMARY KEY (guild_id);


--
-- Name: discord_level_roles discord_level_roles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_level_roles
    ADD CONSTRAINT discord_level_roles_pkey PRIMARY KEY (guild_id, level);


--
-- Name: discord_link_codes discord_link_codes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_link_codes
    ADD CONSTRAINT discord_link_codes_pkey PRIMARY KEY (code);


--
-- Name: discord_logging_config discord_logging_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_logging_config
    ADD CONSTRAINT discord_logging_config_pkey PRIMARY KEY (guild_id);


--
-- Name: discord_mod_cases discord_mod_cases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_mod_cases
    ADD CONSTRAINT discord_mod_cases_pkey PRIMARY KEY (id);


--
-- Name: discord_moderation_config discord_moderation_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_moderation_config
    ADD CONSTRAINT discord_moderation_config_pkey PRIMARY KEY (guild_id);


--
-- Name: discord_panel_messages discord_panel_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_panel_messages
    ADD CONSTRAINT discord_panel_messages_pkey PRIMARY KEY (guild_id, panel_key);


--
-- Name: discord_reaction_roles discord_reaction_roles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_reaction_roles
    ADD CONSTRAINT discord_reaction_roles_pkey PRIMARY KEY (guild_id, message_id, emoji);


--
-- Name: discord_role_aliases discord_role_aliases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_role_aliases
    ADD CONSTRAINT discord_role_aliases_pkey PRIMARY KEY (guild_id, alias);


--
-- Name: discord_starboard_config discord_starboard_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_starboard_config
    ADD CONSTRAINT discord_starboard_config_pkey PRIMARY KEY (guild_id);


--
-- Name: discord_starboard_posts discord_starboard_posts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_starboard_posts
    ADD CONSTRAINT discord_starboard_posts_pkey PRIMARY KEY (guild_id, source_message_id);


--
-- Name: discord_suggestions_config discord_suggestions_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_suggestions_config
    ADD CONSTRAINT discord_suggestions_config_pkey PRIMARY KEY (guild_id);


--
-- Name: discord_suggestions discord_suggestions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_suggestions
    ADD CONSTRAINT discord_suggestions_pkey PRIMARY KEY (id);


--
-- Name: discord_ticket_config discord_ticket_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_ticket_config
    ADD CONSTRAINT discord_ticket_config_pkey PRIMARY KEY (guild_id);


--
-- Name: discord_tickets discord_tickets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_tickets
    ADD CONSTRAINT discord_tickets_pkey PRIMARY KEY (id);


--
-- Name: discord_user_xp discord_user_xp_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_user_xp
    ADD CONSTRAINT discord_user_xp_pkey PRIMARY KEY (guild_id, user_id);


--
-- Name: discord_welcome_config discord_welcome_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_welcome_config
    ADD CONSTRAINT discord_welcome_config_pkey PRIMARY KEY (guild_id);


--
-- Name: forum_replies forum_replies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.forum_replies
    ADD CONSTRAINT forum_replies_pkey PRIMARY KEY (id);


--
-- Name: forum_threads forum_threads_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.forum_threads
    ADD CONSTRAINT forum_threads_pkey PRIMARY KEY (id);


--
-- Name: game_economy_snapshots game_economy_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.game_economy_snapshots
    ADD CONSTRAINT game_economy_snapshots_pkey PRIMARY KEY (id);


--
-- Name: game_tick_logs game_tick_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.game_tick_logs
    ADD CONSTRAINT game_tick_logs_pkey PRIMARY KEY (tick_id);


--
-- Name: gem_packages gem_packages_bmc_extra_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gem_packages
    ADD CONSTRAINT gem_packages_bmc_extra_id_key UNIQUE (bmc_extra_id);


--
-- Name: gem_packages gem_packages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gem_packages
    ADD CONSTRAINT gem_packages_pkey PRIMARY KEY (id);


--
-- Name: gem_purchases gem_purchases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gem_purchases
    ADD CONSTRAINT gem_purchases_pkey PRIMARY KEY (id);


--
-- Name: gem_purchases gem_purchases_stripe_checkout_session_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gem_purchases
    ADD CONSTRAINT gem_purchases_stripe_checkout_session_id_key UNIQUE (stripe_checkout_session_id);


--
-- Name: gem_purchases gem_purchases_stripe_payment_intent_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gem_purchases
    ADD CONSTRAINT gem_purchases_stripe_payment_intent_id_key UNIQUE (stripe_payment_intent_id);


--
-- Name: global_chat_messages global_chat_messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.global_chat_messages
    ADD CONSTRAINT global_chat_messages_pkey PRIMARY KEY (id);


--
-- Name: global_market global_market_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.global_market
    ADD CONSTRAINT global_market_pkey PRIMARY KEY (market_id);


--
-- Name: identity_diagnostic_log identity_diagnostic_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.identity_diagnostic_log
    ADD CONSTRAINT identity_diagnostic_log_pkey PRIMARY KEY (id);


--
-- Name: interactive_events interactive_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interactive_events
    ADD CONSTRAINT interactive_events_pkey PRIMARY KEY (id);


--
-- Name: login_events login_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.login_events
    ADD CONSTRAINT login_events_pkey PRIMARY KEY (id);


--
-- Name: login_verifications login_verifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.login_verifications
    ADD CONSTRAINT login_verifications_pkey PRIMARY KEY (id);


--
-- Name: login_verifications login_verifications_token_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.login_verifications
    ADD CONSTRAINT login_verifications_token_key UNIQUE (token);


--
-- Name: map_combat_log map_combat_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.map_combat_log
    ADD CONSTRAINT map_combat_log_pkey PRIMARY KEY (id);


--
-- Name: map_objects map_objects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.map_objects
    ADD CONSTRAINT map_objects_pkey PRIMARY KEY (id);


--
-- Name: map_objects map_objects_x_y_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.map_objects
    ADD CONSTRAINT map_objects_x_y_key UNIQUE (x, y);


--
-- Name: map_unit_deployments map_unit_deployments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.map_unit_deployments
    ADD CONSTRAINT map_unit_deployments_pkey PRIMARY KEY (id);


--
-- Name: map_unit_deployments map_unit_deployments_province_id_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.map_unit_deployments
    ADD CONSTRAINT map_unit_deployments_province_id_user_id_key UNIQUE (province_id, user_id);


--
-- Name: marches marches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.marches
    ADD CONSTRAINT marches_pkey PRIMARY KEY (id);


--
-- Name: market_auto_order_log market_auto_order_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_auto_order_log
    ADD CONSTRAINT market_auto_order_log_pkey PRIMARY KEY (id);


--
-- Name: market_auto_orders market_auto_orders_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_auto_orders
    ADD CONSTRAINT market_auto_orders_pkey PRIMARY KEY (id);


--
-- Name: market_auto_orders market_auto_orders_user_id_type_resource_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_auto_orders
    ADD CONSTRAINT market_auto_orders_user_id_type_resource_key UNIQUE (user_id, type, resource);


--
-- Name: market_embargoes market_embargoes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_embargoes
    ADD CONSTRAINT market_embargoes_pkey PRIMARY KEY (embargoer_id, embargoed_id);


--
-- Name: market_fills market_fills_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_fills
    ADD CONSTRAINT market_fills_pkey PRIMARY KEY (id);


--
-- Name: market_preferences market_preferences_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_preferences
    ADD CONSTRAINT market_preferences_pkey PRIMARY KEY (user_id);


--
-- Name: military military_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.military
    ADD CONSTRAINT military_pkey PRIMARY KEY (id);


--
-- Name: nation_revenue_history nation_revenue_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nation_revenue_history
    ADD CONSTRAINT nation_revenue_history_pkey PRIMARY KEY (id);


--
-- Name: nation_treaties nation_treaties_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nation_treaties
    ADD CONSTRAINT nation_treaties_pkey PRIMARY KEY (id);


--
-- Name: national_currency_conversions national_currency_conversions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.national_currency_conversions
    ADD CONSTRAINT national_currency_conversions_pkey PRIMARY KEY (id);


--
-- Name: news news_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.news
    ADD CONSTRAINT news_pkey PRIMARY KEY (id);


--
-- Name: node_battles node_battles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_battles
    ADD CONSTRAINT node_battles_pkey PRIMARY KEY (id);


--
-- Name: node_yields node_yields_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_yields
    ADD CONSTRAINT node_yields_pkey PRIMARY KEY (id);


--
-- Name: nodes nodes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nodes
    ADD CONSTRAINT nodes_pkey PRIMARY KEY (id);


--
-- Name: nuclear_strikes nuclear_strikes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nuclear_strikes
    ADD CONSTRAINT nuclear_strikes_pkey PRIMARY KEY (id);


--
-- Name: offers offers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offers
    ADD CONSTRAINT offers_pkey PRIMARY KEY (offer_id);


--
-- Name: patreon_gem_grants patreon_gem_grants_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patreon_gem_grants
    ADD CONSTRAINT patreon_gem_grants_pkey PRIMARY KEY (id);


--
-- Name: patreon_gem_grants patreon_gem_grants_user_id_period_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patreon_gem_grants
    ADD CONSTRAINT patreon_gem_grants_user_id_period_key UNIQUE (user_id, period);


--
-- Name: patreon_tiers patreon_tiers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patreon_tiers
    ADD CONSTRAINT patreon_tiers_pkey PRIMARY KEY (id);


--
-- Name: patreon_tiers patreon_tiers_title_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patreon_tiers
    ADD CONSTRAINT patreon_tiers_title_key UNIQUE (title);


--
-- Name: peace peace_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.peace
    ADD CONSTRAINT peace_pkey PRIMARY KEY (id);


--
-- Name: player_reimbursements player_reimbursements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.player_reimbursements
    ADD CONSTRAINT player_reimbursements_pkey PRIMARY KEY (reimbursement_id);


--
-- Name: policies policies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policies
    ADD CONSTRAINT policies_pkey PRIMARY KEY (user_id);


--
-- Name: poll_votes poll_votes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.poll_votes
    ADD CONSTRAINT poll_votes_pkey PRIMARY KEY (user_id, poll_name);


--
-- Name: population_growth_freezes population_growth_freezes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.population_growth_freezes
    ADD CONSTRAINT population_growth_freezes_pkey PRIMARY KEY (user_id);


--
-- Name: proinfra proinfra_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proinfra
    ADD CONSTRAINT proinfra_pkey PRIMARY KEY (id);


--
-- Name: province_iron_domes province_iron_domes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.province_iron_domes
    ADD CONSTRAINT province_iron_domes_pkey PRIMARY KEY (province_id);


--
-- Name: provinces provinces_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provinces
    ADD CONSTRAINT provinces_pkey PRIMARY KEY (id);


--
-- Name: purchase_audit purchase_audit_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.purchase_audit
    ADD CONSTRAINT purchase_audit_pkey PRIMARY KEY (id);


--
-- Name: referral_active_days referral_active_days_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_active_days
    ADD CONSTRAINT referral_active_days_pkey PRIMARY KEY (referred_user_id, activity_date);


--
-- Name: referral_milestone_payouts referral_milestone_payouts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_milestone_payouts
    ADD CONSTRAINT referral_milestone_payouts_pkey PRIMARY KEY (id);


--
-- Name: referral_milestone_payouts referral_milestone_payouts_referrer_user_id_referred_user_i_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_milestone_payouts
    ADD CONSTRAINT referral_milestone_payouts_referrer_user_id_referred_user_i_key UNIQUE (referrer_user_id, referred_user_id, milestone_days);


--
-- Name: repairs repairs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.repairs
    ADD CONSTRAINT repairs_pkey PRIMARY KEY (id);


--
-- Name: reparation_tax reparation_tax_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reparation_tax
    ADD CONSTRAINT reparation_tax_pkey PRIMARY KEY (id);


--
-- Name: reset_codes reset_codes_url_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reset_codes
    ADD CONSTRAINT reset_codes_url_code_key UNIQUE (url_code);


--
-- Name: reset_codes reset_codes_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reset_codes
    ADD CONSTRAINT reset_codes_user_id_key UNIQUE (user_id);


--
-- Name: resource_dictionary resource_dictionary_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_dictionary
    ADD CONSTRAINT resource_dictionary_name_key UNIQUE (name);


--
-- Name: resource_dictionary resource_dictionary_name_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_dictionary
    ADD CONSTRAINT resource_dictionary_name_unique UNIQUE (name);


--
-- Name: resource_dictionary resource_dictionary_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_dictionary
    ADD CONSTRAINT resource_dictionary_pkey PRIMARY KEY (resource_id);


--
-- Name: resource_dictionary resource_unique_display_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resource_dictionary
    ADD CONSTRAINT resource_unique_display_name UNIQUE (display_name);


--
-- Name: resources resources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resources
    ADD CONSTRAINT resources_pkey PRIMARY KEY (id);


--
-- Name: revenue revenue_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.revenue
    ADD CONSTRAINT revenue_pkey PRIMARY KEY (id);


--
-- Name: schema_migrations schema_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.schema_migrations
    ADD CONSTRAINT schema_migrations_pkey PRIMARY KEY (name);


--
-- Name: signup_attempts signup_attempts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signup_attempts
    ADD CONSTRAINT signup_attempts_pkey PRIMARY KEY (id);


--
-- Name: site_visits site_visits_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.site_visits
    ADD CONSTRAINT site_visits_pkey PRIMARY KEY (id);


--
-- Name: spyinfo spyinfo_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.spyinfo
    ADD CONSTRAINT spyinfo_pkey PRIMARY KEY (id);


--
-- Name: stats stats_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stats
    ADD CONSTRAINT stats_pkey PRIMARY KEY (id);


--
-- Name: task_cursors task_cursors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_cursors
    ADD CONSTRAINT task_cursors_pkey PRIMARY KEY (task_name);


--
-- Name: task_metrics task_metrics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_metrics
    ADD CONSTRAINT task_metrics_pkey PRIMARY KEY (id);


--
-- Name: task_runs task_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_runs
    ADD CONSTRAINT task_runs_pkey PRIMARY KEY (task_name);


--
-- Name: tech_dictionary tech_dictionary_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tech_dictionary
    ADD CONSTRAINT tech_dictionary_name_key UNIQUE (name);


--
-- Name: tech_dictionary tech_dictionary_name_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tech_dictionary
    ADD CONSTRAINT tech_dictionary_name_unique UNIQUE (name);


--
-- Name: tech_dictionary tech_dictionary_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tech_dictionary
    ADD CONSTRAINT tech_dictionary_pkey PRIMARY KEY (tech_id);


--
-- Name: totp_backup_codes totp_backup_codes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.totp_backup_codes
    ADD CONSTRAINT totp_backup_codes_pkey PRIMARY KEY (id);


--
-- Name: trade_agreements trade_agreements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trade_agreements
    ADD CONSTRAINT trade_agreements_pkey PRIMARY KEY (id);


--
-- Name: trade_events trade_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trade_events
    ADD CONSTRAINT trade_events_pkey PRIMARY KEY (id);


--
-- Name: trades trades_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trades
    ADD CONSTRAINT trades_pkey PRIMARY KEY (offer_id);


--
-- Name: treaties treaties_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treaties
    ADD CONSTRAINT treaties_pkey PRIMARY KEY (id);


--
-- Name: unit_dictionary unit_dictionary_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.unit_dictionary
    ADD CONSTRAINT unit_dictionary_name_key UNIQUE (name);


--
-- Name: unit_dictionary unit_dictionary_name_unique; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.unit_dictionary
    ADD CONSTRAINT unit_dictionary_name_unique UNIQUE (name);


--
-- Name: unit_dictionary unit_dictionary_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.unit_dictionary
    ADD CONSTRAINT unit_dictionary_pkey PRIMARY KEY (unit_id);


--
-- Name: upgrades upgrades_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.upgrades
    ADD CONSTRAINT upgrades_pkey PRIMARY KEY (user_id);


--
-- Name: user_achievements user_achievements_user_id_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_achievements
    ADD CONSTRAINT user_achievements_user_id_key_key UNIQUE (user_id, key);


--
-- Name: user_active_days user_active_days_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_active_days
    ADD CONSTRAINT user_active_days_pkey PRIMARY KEY (user_id, day);


--
-- Name: user_buildings user_buildings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_buildings
    ADD CONSTRAINT user_buildings_pkey PRIMARY KEY (user_id, building_id, province_id);


--
-- Name: user_cosmetics user_cosmetics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_cosmetics
    ADD CONSTRAINT user_cosmetics_pkey PRIMARY KEY (id);


--
-- Name: user_cosmetics user_cosmetics_user_id_cosmetic_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_cosmetics
    ADD CONSTRAINT user_cosmetics_user_id_cosmetic_id_key UNIQUE (user_id, cosmetic_id);


--
-- Name: user_economy user_economy_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_economy
    ADD CONSTRAINT user_economy_pkey PRIMARY KEY (user_id, resource_id);


--
-- Name: user_loans user_loans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_loans
    ADD CONSTRAINT user_loans_pkey PRIMARY KEY (id);


--
-- Name: user_military user_military_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_military
    ADD CONSTRAINT user_military_pkey PRIMARY KEY (user_id, unit_id);


--
-- Name: user_tech user_tech_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_tech
    ADD CONSTRAINT user_tech_pkey PRIMARY KEY (user_id, tech_id);


--
-- Name: user_unit_stockpile user_unit_stockpile_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_unit_stockpile
    ADD CONSTRAINT user_unit_stockpile_pkey PRIMARY KEY (user_id, unit_id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_join_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_join_number_key UNIQUE (join_number);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_referral_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_referral_code_key UNIQUE (referral_code);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: war_events war_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.war_events
    ADD CONSTRAINT war_events_pkey PRIMARY KEY (id);


--
-- Name: wars_normalized wars_normalized_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wars_normalized
    ADD CONSTRAINT wars_normalized_pkey PRIMARY KEY (war_id);


--
-- Name: wars wars_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wars
    ADD CONSTRAINT wars_pkey PRIMARY KEY (id);


--
-- Name: world_events world_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.world_events
    ADD CONSTRAINT world_events_pkey PRIMARY KEY (id);


--
-- Name: coalitions_userid_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX coalitions_userid_idx ON public.coalitions_legacy USING btree (userid);


--
-- Name: currency_union_members_union_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX currency_union_members_union_idx ON public.currency_union_members USING btree (union_id);


--
-- Name: currency_unions_name_lower_uniq; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX currency_unions_name_lower_uniq ON public.currency_unions USING btree (lower((name)::text));


--
-- Name: idx_admin_actions_actor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_admin_actions_actor ON public.admin_actions USING btree (actor);


--
-- Name: idx_admin_actions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_admin_actions_user_id ON public.admin_actions USING btree (user_id);


--
-- Name: idx_admin_user_controls_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_admin_user_controls_user_id ON public.admin_user_controls USING btree (user_id);


--
-- Name: idx_bmc_gem_purchases_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bmc_gem_purchases_status ON public.bmc_gem_purchases USING btree (status);


--
-- Name: idx_bmc_gem_purchases_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bmc_gem_purchases_user_id ON public.bmc_gem_purchases USING btree (user_id);


--
-- Name: idx_bonds_issuer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bonds_issuer ON public.bonds USING btree (issuer_id);


--
-- Name: idx_bonds_lender; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bonds_lender ON public.bonds USING btree (lender_id);


--
-- Name: idx_bonds_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bonds_status ON public.bonds USING btree (status);


--
-- Name: idx_bounties_poster; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bounties_poster ON public.bounties USING btree (poster_id);


--
-- Name: idx_bounties_target_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bounties_target_status ON public.bounties USING btree (target_id, status);


--
-- Name: idx_building_dictionary_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_building_dictionary_name ON public.building_dictionary USING btree (name);


--
-- Name: idx_cbr_colid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cbr_colid ON public.colbanksrequests USING btree (colid);


--
-- Name: idx_cbr_reqid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_cbr_reqid ON public.colbanksrequests USING btree (reqid);


--
-- Name: idx_coalition_bond_insurance_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_coalition_bond_insurance_user ON public.coalition_bond_insurance USING btree (user_id);


--
-- Name: idx_coalition_invites_coalition; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_coalition_invites_coalition ON public.coalition_invites USING btree (coalition_id, status);


--
-- Name: idx_coalition_invites_coalition_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_coalition_invites_coalition_id ON public.coalition_invites USING btree (coalition_id);


--
-- Name: idx_coalition_invites_coalition_user_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_coalition_invites_coalition_user_status ON public.coalition_invites USING btree (coalition_id, invited_user_id, status);


--
-- Name: idx_coalition_invites_invited_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_coalition_invites_invited_user ON public.coalition_invites USING btree (invited_user_id, status);


--
-- Name: idx_coalition_invites_invited_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_coalition_invites_invited_user_id ON public.coalition_invites USING btree (invited_user_id);


--
-- Name: idx_coalition_invites_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_coalition_invites_status ON public.coalition_invites USING btree (status);


--
-- Name: idx_coalition_members_coalition_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_coalition_members_coalition_id ON public.coalition_members USING btree (coalition_id);


--
-- Name: idx_coalition_members_role; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_coalition_members_role ON public.coalition_members USING btree (role);


--
-- Name: idx_coalition_members_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_coalition_members_user_id ON public.coalition_members USING btree (user_id);


--
-- Name: idx_coalition_messages_coalition_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_coalition_messages_coalition_created ON public.coalition_messages USING btree (coalition_id, created_at);


--
-- Name: idx_coalitions_colid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_coalitions_colid ON public.coalitions_legacy USING btree (colid);


--
-- Name: idx_coalitions_legacy_colid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_coalitions_legacy_colid ON public.coalitions_legacy USING btree (colid);


--
-- Name: idx_coalitions_legacy_userid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_coalitions_legacy_userid ON public.coalitions_legacy USING btree (userid);


--
-- Name: idx_col_applications_colid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_col_applications_colid ON public.col_applications USING btree (colid);


--
-- Name: idx_col_applications_userid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_col_applications_userid ON public.col_applications USING btree (userid);


--
-- Name: idx_col_bank_recurring_trade_runs_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_col_bank_recurring_trade_runs_time ON public.col_bank_recurring_trade_runs USING btree (recurring_trade_id, executed_at DESC);


--
-- Name: idx_col_bank_recurring_trades_coalition; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_col_bank_recurring_trades_coalition ON public.col_bank_recurring_trades USING btree (coalition_id, status);


--
-- Name: idx_col_bank_recurring_trades_due; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_col_bank_recurring_trades_due ON public.col_bank_recurring_trades USING btree (next_execution_at) WHERE (status = 'active'::text);


--
-- Name: idx_col_bank_recurring_trades_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_col_bank_recurring_trades_user ON public.col_bank_recurring_trades USING btree (user_id);


--
-- Name: idx_col_bank_trades_coalition_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_col_bank_trades_coalition_status ON public.col_bank_trades USING btree (coalition_id, status);


--
-- Name: idx_col_bank_trades_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_col_bank_trades_user ON public.col_bank_trades USING btree (user_id);


--
-- Name: idx_col_bank_transactions_coalition_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_col_bank_transactions_coalition_time ON public.col_bank_transactions USING btree (coalition_id, created_at DESC);


--
-- Name: idx_colbanks_colid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_colbanks_colid ON public.colbanks USING btree (colid);


--
-- Name: idx_colbanksrequests_colid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_colbanksrequests_colid ON public.colbanksrequests USING btree (colid);


--
-- Name: idx_colbanksrequests_reqid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_colbanksrequests_reqid ON public.colbanksrequests USING btree (reqid);


--
-- Name: idx_currency_holdings_issuer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_currency_holdings_issuer ON public.currency_holdings USING btree (issuer_id);


--
-- Name: idx_currency_market_offers_issuer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_currency_market_offers_issuer ON public.currency_market_offers USING btree (issuer_id, type, price_gold);


--
-- Name: idx_currency_market_offers_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_currency_market_offers_user ON public.currency_market_offers USING btree (user_id);


--
-- Name: idx_currency_market_trades_issuer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_currency_market_trades_issuer ON public.currency_market_trades USING btree (issuer_id, created_at DESC);


--
-- Name: idx_devlog_entries_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_devlog_entries_created ON public.devlog_entries USING btree (created_at DESC);


--
-- Name: idx_direct_messages_recipient_sender_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_direct_messages_recipient_sender_created ON public.direct_messages USING btree (recipient_id, sender_id, created_at);


--
-- Name: idx_direct_messages_recipient_unread; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_direct_messages_recipient_unread ON public.direct_messages USING btree (recipient_id) WHERE (read_at IS NULL);


--
-- Name: idx_direct_messages_sender_recipient_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_direct_messages_sender_recipient_created ON public.direct_messages USING btree (sender_id, recipient_id, created_at);


--
-- Name: idx_discord_custom_commands_guild; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_discord_custom_commands_guild ON public.discord_custom_commands USING btree (guild_id);


--
-- Name: idx_discord_giveaways_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_discord_giveaways_active ON public.discord_giveaways USING btree (ends_at) WHERE (ended = false);


--
-- Name: idx_discord_guild_settings_guild_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_discord_guild_settings_guild_id ON public.discord_guild_settings USING btree (guild_id);


--
-- Name: idx_discord_link_codes_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_discord_link_codes_user_id ON public.discord_link_codes USING btree (user_id);


--
-- Name: idx_discord_mod_cases_guild_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_discord_mod_cases_guild_created ON public.discord_mod_cases USING btree (guild_id, created_at DESC);


--
-- Name: idx_discord_mod_cases_guild_target; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_discord_mod_cases_guild_target ON public.discord_mod_cases USING btree (guild_id, target_user_id);


--
-- Name: idx_discord_role_aliases_guild_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_discord_role_aliases_guild_id ON public.discord_role_aliases USING btree (guild_id);


--
-- Name: idx_discord_suggestions_guild_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_discord_suggestions_guild_status ON public.discord_suggestions USING btree (guild_id, status);


--
-- Name: idx_discord_tickets_guild_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_discord_tickets_guild_status ON public.discord_tickets USING btree (guild_id, status);


--
-- Name: idx_economy_snapshots_time_resource; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_economy_snapshots_time_resource ON public.game_economy_snapshots USING btree (resource_name, snapshot_time DESC);


--
-- Name: idx_forum_replies_thread_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_forum_replies_thread_created ON public.forum_replies USING btree (thread_id, created_at);


--
-- Name: idx_forum_threads_last_activity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_forum_threads_last_activity ON public.forum_threads USING btree (last_activity_at DESC);


--
-- Name: idx_game_economy_snapshots_resource; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_game_economy_snapshots_resource ON public.game_economy_snapshots USING btree (resource_name);


--
-- Name: idx_game_tick_logs_started_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_game_tick_logs_started_at ON public.game_tick_logs USING btree (started_at DESC);


--
-- Name: idx_game_tick_logs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_game_tick_logs_status ON public.game_tick_logs USING btree (status);


--
-- Name: idx_gem_purchases_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_gem_purchases_status ON public.gem_purchases USING btree (status);


--
-- Name: idx_gem_purchases_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_gem_purchases_user_id ON public.gem_purchases USING btree (user_id);


--
-- Name: idx_global_chat_messages_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_global_chat_messages_created ON public.global_chat_messages USING btree (created_at);


--
-- Name: idx_global_market_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_global_market_created_at ON public.global_market USING btree (created_at DESC);


--
-- Name: idx_global_market_offer_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_global_market_offer_type ON public.global_market USING btree (offer_type);


--
-- Name: idx_global_market_resource_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_global_market_resource_id ON public.global_market USING btree (resource_id);


--
-- Name: idx_global_market_seller_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_global_market_seller_id ON public.global_market USING btree (seller_id);


--
-- Name: idx_global_market_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_global_market_status ON public.global_market USING btree (status);


--
-- Name: idx_identity_diag_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_identity_diag_created_at ON public.identity_diagnostic_log USING btree (created_at);


--
-- Name: idx_identity_diag_severity; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_identity_diag_severity ON public.identity_diagnostic_log USING btree (severity) WHERE (severity <> 'info'::text);


--
-- Name: idx_identity_diag_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_identity_diag_user_id ON public.identity_diagnostic_log USING btree (session_user_id);


--
-- Name: idx_login_events_ip; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_login_events_ip ON public.login_events USING btree (ip);


--
-- Name: idx_login_events_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_login_events_user_id ON public.login_events USING btree (user_id);


--
-- Name: idx_login_verifications_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_login_verifications_user_id ON public.login_verifications USING btree (user_id);


--
-- Name: idx_map_clog_prov; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_map_clog_prov ON public.map_combat_log USING btree (province_id);


--
-- Name: idx_map_clog_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_map_clog_time ON public.map_combat_log USING btree (occurred_at DESC);


--
-- Name: idx_map_dep_prov; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_map_dep_prov ON public.map_unit_deployments USING btree (province_id);


--
-- Name: idx_map_dep_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_map_dep_user ON public.map_unit_deployments USING btree (user_id);


--
-- Name: idx_map_objects_owner; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_map_objects_owner ON public.map_objects USING btree (owner_id);


--
-- Name: idx_marches_target; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_marches_target ON public.marches USING btree (target_id);


--
-- Name: idx_marches_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_marches_user ON public.marches USING btree (user_id);


--
-- Name: idx_market_auto_order_log_rule_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_market_auto_order_log_rule_time ON public.market_auto_order_log USING btree (auto_order_id, created_at);


--
-- Name: idx_market_auto_orders_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_market_auto_orders_active ON public.market_auto_orders USING btree (id) WHERE active;


--
-- Name: idx_market_embargoes_embargoed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_market_embargoes_embargoed ON public.market_embargoes USING btree (embargoed_id);


--
-- Name: idx_market_fills_resource_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_market_fills_resource_time ON public.market_fills USING btree (resource, created_at DESC);


--
-- Name: idx_nation_revenue_history_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_nation_revenue_history_time ON public.nation_revenue_history USING btree (recorded_at);


--
-- Name: idx_nation_revenue_history_user_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_nation_revenue_history_user_time ON public.nation_revenue_history USING btree (user_id, recorded_at DESC);


--
-- Name: idx_national_currency_conversions_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_national_currency_conversions_user_id ON public.national_currency_conversions USING btree (user_id);


--
-- Name: idx_news_dest; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_news_dest ON public.news USING btree (destination_id);


--
-- Name: idx_news_dest_is_read; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_news_dest_is_read ON public.news USING btree (destination_id, is_read);


--
-- Name: idx_news_destination_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_news_destination_id ON public.news USING btree (destination_id);


--
-- Name: idx_node_battles_node_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_node_battles_node_id ON public.node_battles USING btree (node_id);


--
-- Name: idx_node_battles_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_node_battles_status ON public.node_battles USING btree (status, resolves_at);


--
-- Name: idx_nodes_controlling_coalition; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_nodes_controlling_coalition ON public.nodes USING btree (controlling_coalition_id);


--
-- Name: idx_nuclear_strikes_attacker_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_nuclear_strikes_attacker_time ON public.nuclear_strikes USING btree (attacker_id, launched_at DESC);


--
-- Name: idx_nuclear_strikes_province_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_nuclear_strikes_province_time ON public.nuclear_strikes USING btree (province_id, launched_at DESC);


--
-- Name: idx_nuclear_strikes_war; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_nuclear_strikes_war ON public.nuclear_strikes USING btree (war_id, launched_at);


--
-- Name: idx_offers_resource_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_offers_resource_type ON public.offers USING btree (resource, type);


--
-- Name: idx_offers_resource_type_price_offerid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_offers_resource_type_price_offerid ON public.offers USING btree (resource, type, price, offer_id);


--
-- Name: idx_offers_type_resource; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_offers_type_resource ON public.offers USING btree (type, resource);


--
-- Name: idx_offers_type_resource_price_offerid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_offers_type_resource_price_offerid ON public.offers USING btree (type, resource, price, offer_id);


--
-- Name: idx_offers_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_offers_user_id ON public.offers USING btree (user_id);


--
-- Name: idx_offers_user_id_offer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_offers_user_id_offer_id ON public.offers USING btree (user_id, offer_id);


--
-- Name: idx_patreon_gem_grants_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_patreon_gem_grants_user_id ON public.patreon_gem_grants USING btree (user_id);


--
-- Name: idx_peace_author; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_peace_author ON public.peace USING btree (author);


--
-- Name: idx_policies_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_policies_user_id ON public.policies USING btree (user_id);


--
-- Name: idx_poll_votes_poll_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_poll_votes_poll_name ON public.poll_votes USING btree (poll_name);


--
-- Name: idx_poll_votes_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_poll_votes_user_id ON public.poll_votes USING btree (user_id);


--
-- Name: idx_province_coordinates; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_province_coordinates ON public.provinces USING btree (coordinate_x, coordinate_y) WHERE ((coordinate_x IS NOT NULL) AND (coordinate_y IS NOT NULL));


--
-- Name: idx_provinces_one_capital_per_user; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_provinces_one_capital_per_user ON public.provinces USING btree (userid) WHERE is_capital;


--
-- Name: idx_provinces_pop_children; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_provinces_pop_children ON public.provinces USING btree (pop_children);


--
-- Name: idx_provinces_pop_elderly; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_provinces_pop_elderly ON public.provinces USING btree (pop_elderly);


--
-- Name: idx_provinces_pop_working; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_provinces_pop_working ON public.provinces USING btree (pop_working);


--
-- Name: idx_provinces_userid_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_provinces_userid_id ON public.provinces USING btree (userid, id);


--
-- Name: idx_provinces_userid_population; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_provinces_userid_population ON public.provinces USING btree (userid, population);


--
-- Name: idx_purchase_audit_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_purchase_audit_user_id ON public.purchase_audit USING btree (user_id);


--
-- Name: idx_referral_payouts_referrer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_referral_payouts_referrer ON public.referral_milestone_payouts USING btree (referrer_user_id);


--
-- Name: idx_reparation_tax_loser; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_reparation_tax_loser ON public.reparation_tax USING btree (loser);


--
-- Name: idx_reparation_tax_winner; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_reparation_tax_winner ON public.reparation_tax USING btree (winner);


--
-- Name: idx_reptax_loser; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_reptax_loser ON public.reparation_tax USING btree (loser);


--
-- Name: idx_reptax_winner; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_reptax_winner ON public.reparation_tax USING btree (winner);


--
-- Name: idx_requests_colid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_requests_colid ON public.requests USING btree (colid);


--
-- Name: idx_requests_reqid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_requests_reqid ON public.requests USING btree (reqid);


--
-- Name: idx_revenue_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_revenue_user_id ON public.revenue USING btree (user_id);


--
-- Name: idx_spyinfo_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_spyinfo_date ON public.spyinfo USING btree (date);


--
-- Name: idx_spyinfo_spyee; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_spyinfo_spyee ON public.spyinfo USING btree (spyee);


--
-- Name: idx_spyinfo_spyer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_spyinfo_spyer ON public.spyinfo USING btree (spyer);


--
-- Name: idx_spyinfo_spyer_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_spyinfo_spyer_date ON public.spyinfo USING btree (spyer, date);


--
-- Name: idx_spyinfo_spyer_type_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_spyinfo_spyer_type_date ON public.spyinfo USING btree (spyer, spy_type, date DESC);


--
-- Name: idx_stats_gold; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stats_gold ON public.stats USING btree (gold);


--
-- Name: idx_stats_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_stats_id ON public.stats USING btree (id);


--
-- Name: idx_task_runs_task_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_runs_task_name ON public.task_runs USING btree (task_name);


--
-- Name: idx_tech_prerequisite; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_tech_prerequisite ON public.tech_dictionary USING btree (prerequisite_tech_id);


--
-- Name: idx_totp_backup_codes_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_totp_backup_codes_user_id ON public.totp_backup_codes USING btree (user_id);


--
-- Name: idx_trade_agreements_next_exec; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_trade_agreements_next_exec ON public.trade_agreements USING btree (next_execution) WHERE (status = 'active'::text);


--
-- Name: idx_trade_agreements_proposer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_trade_agreements_proposer ON public.trade_agreements USING btree (proposer_id);


--
-- Name: idx_trade_agreements_receiver; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_trade_agreements_receiver ON public.trade_agreements USING btree (receiver_id);


--
-- Name: idx_trade_agreements_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_trade_agreements_status ON public.trade_agreements USING btree (status);


--
-- Name: idx_trades_offer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_trades_offer_id ON public.trades USING btree (offer_id);


--
-- Name: idx_trades_offeree; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_trades_offeree ON public.trades USING btree (offeree);


--
-- Name: idx_trades_offeree_offer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_trades_offeree_offer_id ON public.trades USING btree (offeree, offer_id);


--
-- Name: idx_trades_offerer; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_trades_offerer ON public.trades USING btree (offerer);


--
-- Name: idx_trades_offerer_offer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_trades_offerer_offer_id ON public.trades USING btree (offerer, offer_id);


--
-- Name: idx_treaties_col1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_treaties_col1 ON public.treaties USING btree (col1_id);


--
-- Name: idx_treaties_col1_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_treaties_col1_id ON public.treaties USING btree (col1_id);


--
-- Name: idx_treaties_col2; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_treaties_col2 ON public.treaties USING btree (col2_id);


--
-- Name: idx_treaties_col2_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_treaties_col2_id ON public.treaties USING btree (col2_id);


--
-- Name: idx_treaties_col2_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_treaties_col2_status ON public.treaties USING btree (col2_id, status);


--
-- Name: idx_treaties_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_treaties_status ON public.treaties USING btree (status);


--
-- Name: idx_unit_dictionary_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_unit_dictionary_name ON public.unit_dictionary USING btree (name);


--
-- Name: idx_user_buildings_building_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_buildings_building_id ON public.user_buildings USING btree (building_id);


--
-- Name: idx_user_buildings_province_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_buildings_province_id ON public.user_buildings USING btree (province_id);


--
-- Name: idx_user_buildings_user_building_province; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_buildings_user_building_province ON public.user_buildings USING btree (user_id, building_id, province_id);


--
-- Name: idx_user_buildings_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_buildings_user_id ON public.user_buildings USING btree (user_id);


--
-- Name: idx_user_buildings_user_province; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_buildings_user_province ON public.user_buildings USING btree (user_id, province_id);


--
-- Name: idx_user_cosmetics_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_cosmetics_user_id ON public.user_cosmetics USING btree (user_id);


--
-- Name: idx_user_economy_resource_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_economy_resource_id ON public.user_economy USING btree (resource_id);


--
-- Name: idx_user_economy_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_economy_user_id ON public.user_economy USING btree (user_id);


--
-- Name: idx_user_economy_user_resource; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_economy_user_resource ON public.user_economy USING btree (user_id, resource_id);


--
-- Name: idx_user_loans_one_active; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_user_loans_one_active ON public.user_loans USING btree (user_id) WHERE (status = 'active'::text);


--
-- Name: idx_user_loans_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_loans_user_id ON public.user_loans USING btree (user_id);


--
-- Name: idx_user_military_combat_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_military_combat_type ON public.unit_dictionary USING btree (combat_type);


--
-- Name: idx_user_military_unit_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_military_unit_id ON public.user_military USING btree (unit_id);


--
-- Name: idx_user_military_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_military_user_id ON public.user_military USING btree (user_id);


--
-- Name: idx_user_military_user_unit; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_military_user_unit ON public.user_military USING btree (user_id, unit_id);


--
-- Name: idx_user_tech_tech_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_tech_tech_id ON public.user_tech USING btree (tech_id);


--
-- Name: idx_user_tech_unlocked; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_tech_unlocked ON public.user_tech USING btree (user_id, is_unlocked);


--
-- Name: idx_user_tech_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_tech_user_id ON public.user_tech USING btree (user_id);


--
-- Name: idx_user_tech_user_unlocked; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_tech_user_unlocked ON public.user_tech USING btree (user_id, is_unlocked);


--
-- Name: idx_user_unit_stockpile_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_unit_stockpile_user_id ON public.user_unit_stockpile USING btree (user_id);


--
-- Name: idx_users_discord_id_unique; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_users_discord_id_unique ON public.users USING btree (discord_id) WHERE ((discord_id IS NOT NULL) AND ((discord_id)::text <> ''::text));


--
-- Name: idx_users_join_number; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_join_number ON public.users USING btree (join_number);


--
-- Name: idx_users_last_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_last_active ON public.users USING btree (last_active);


--
-- Name: idx_users_referred_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_referred_by ON public.users USING btree (referred_by_user_id);


--
-- Name: idx_users_username; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_users_username ON public.users USING btree (username);


--
-- Name: idx_wars_attacker_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wars_attacker_id ON public.wars_normalized USING btree (attacker_id);


--
-- Name: idx_wars_defender; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wars_defender ON public.wars USING btree (defender);


--
-- Name: idx_wars_defender_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wars_defender_id ON public.wars_normalized USING btree (defender_id);


--
-- Name: idx_wars_peace_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wars_peace_date ON public.wars USING btree (peace_date);


--
-- Name: idx_wars_peace_offer_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wars_peace_offer_id ON public.wars USING btree (peace_offer_id);


--
-- Name: idx_wars_start_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wars_start_date ON public.wars_normalized USING btree (start_date DESC);


--
-- Name: idx_wars_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wars_status ON public.wars_normalized USING btree (status);


--
-- Name: idx_wars_user_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_wars_user_active ON public.wars_normalized USING btree (attacker_id, defender_id, status) WHERE ((status)::text = 'active'::text);


--
-- Name: idx_world_events_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_world_events_created_at ON public.world_events USING btree (created_at DESC);


--
-- Name: offers_price_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX offers_price_idx ON public.offers USING btree (price);


--
-- Name: offers_resource_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX offers_resource_idx ON public.offers USING btree (resource);


--
-- Name: offers_user_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX offers_user_id_idx ON public.offers USING btree (user_id);


--
-- Name: provinces_userid_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX provinces_userid_idx ON public.provinces USING btree (userid);


--
-- Name: site_visits_day_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX site_visits_day_idx ON public.site_visits USING btree (day);


--
-- Name: trades_offer_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX trades_offer_id_idx ON public.trades USING btree (offer_id);


--
-- Name: user_achievements_user_id_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX user_achievements_user_id_idx ON public.user_achievements USING btree (user_id);


--
-- Name: user_active_days_day_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX user_active_days_day_idx ON public.user_active_days USING btree (day);


--
-- Name: wars_attacker_defender_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX wars_attacker_defender_idx ON public.wars USING btree (attacker, defender);


--
-- Name: provinces trg_audit_province_delete; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_audit_province_delete AFTER DELETE ON public.provinces FOR EACH ROW EXECUTE FUNCTION public.audit_province_delete();


--
-- Name: provinces trg_sync_province_population; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_sync_province_population BEFORE UPDATE ON public.provinces FOR EACH ROW EXECUTE FUNCTION public.sync_province_population();


--
-- Name: provinces trg_sync_province_population_insert; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_sync_province_population_insert BEFORE INSERT ON public.provinces FOR EACH ROW EXECUTE FUNCTION public.sync_province_population_insert();


--
-- Name: admin_user_controls admin_user_controls_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_user_controls
    ADD CONSTRAINT admin_user_controls_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: advertisements advertisements_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.advertisements
    ADD CONSTRAINT advertisements_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: assembly_effects assembly_effects_proposal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assembly_effects
    ADD CONSTRAINT assembly_effects_proposal_id_fkey FOREIGN KEY (proposal_id) REFERENCES public.assembly_proposals(id) ON DELETE CASCADE;


--
-- Name: assembly_effects assembly_effects_target_nation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assembly_effects
    ADD CONSTRAINT assembly_effects_target_nation_id_fkey FOREIGN KEY (target_nation_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: assembly_proposals assembly_proposals_proposer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assembly_proposals
    ADD CONSTRAINT assembly_proposals_proposer_id_fkey FOREIGN KEY (proposer_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: assembly_proposals assembly_proposals_target_nation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assembly_proposals
    ADD CONSTRAINT assembly_proposals_target_nation_id_fkey FOREIGN KEY (target_nation_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: assembly_votes assembly_votes_proposal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assembly_votes
    ADD CONSTRAINT assembly_votes_proposal_id_fkey FOREIGN KEY (proposal_id) REFERENCES public.assembly_proposals(id) ON DELETE CASCADE;


--
-- Name: assembly_votes assembly_votes_voter_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assembly_votes
    ADD CONSTRAINT assembly_votes_voter_id_fkey FOREIGN KEY (voter_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: bmc_gem_purchases bmc_gem_purchases_gem_package_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bmc_gem_purchases
    ADD CONSTRAINT bmc_gem_purchases_gem_package_id_fkey FOREIGN KEY (gem_package_id) REFERENCES public.gem_packages(id);


--
-- Name: bmc_gem_purchases bmc_gem_purchases_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bmc_gem_purchases
    ADD CONSTRAINT bmc_gem_purchases_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: bonds bonds_issuer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bonds
    ADD CONSTRAINT bonds_issuer_id_fkey FOREIGN KEY (issuer_id) REFERENCES public.users(id);


--
-- Name: bonds bonds_lender_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bonds
    ADD CONSTRAINT bonds_lender_id_fkey FOREIGN KEY (lender_id) REFERENCES public.users(id);


--
-- Name: bounties bounties_claimed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bounties
    ADD CONSTRAINT bounties_claimed_by_fkey FOREIGN KEY (claimed_by) REFERENCES public.users(id);


--
-- Name: bounties bounties_poster_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bounties
    ADD CONSTRAINT bounties_poster_id_fkey FOREIGN KEY (poster_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: bounties bounties_target_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bounties
    ADD CONSTRAINT bounties_target_id_fkey FOREIGN KEY (target_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: coalition_bond_insurance coalition_bond_insurance_added_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalition_bond_insurance
    ADD CONSTRAINT coalition_bond_insurance_added_by_fkey FOREIGN KEY (added_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: coalition_bond_insurance coalition_bond_insurance_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalition_bond_insurance
    ADD CONSTRAINT coalition_bond_insurance_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: coalition_invites coalition_invites_coalition_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalition_invites
    ADD CONSTRAINT coalition_invites_coalition_id_fkey FOREIGN KEY (coalition_id) REFERENCES public.colnames(id) ON DELETE CASCADE;


--
-- Name: coalition_invites coalition_invites_invited_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalition_invites
    ADD CONSTRAINT coalition_invites_invited_by_user_id_fkey FOREIGN KEY (invited_by_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: coalition_invites coalition_invites_invited_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalition_invites
    ADD CONSTRAINT coalition_invites_invited_user_id_fkey FOREIGN KEY (invited_user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: coalition_messages coalition_messages_coalition_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalition_messages
    ADD CONSTRAINT coalition_messages_coalition_id_fkey FOREIGN KEY (coalition_id) REFERENCES public.colnames(id) ON DELETE CASCADE;


--
-- Name: coalition_messages coalition_messages_sender_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalition_messages
    ADD CONSTRAINT coalition_messages_sender_id_fkey FOREIGN KEY (sender_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: col_bank_recurring_trade_runs col_bank_recurring_trade_runs_recurring_trade_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.col_bank_recurring_trade_runs
    ADD CONSTRAINT col_bank_recurring_trade_runs_recurring_trade_id_fkey FOREIGN KEY (recurring_trade_id) REFERENCES public.col_bank_recurring_trades(id) ON DELETE CASCADE;


--
-- Name: col_bank_recurring_trades col_bank_recurring_trades_approved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.col_bank_recurring_trades
    ADD CONSTRAINT col_bank_recurring_trades_approved_by_fkey FOREIGN KEY (approved_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: col_bank_recurring_trades col_bank_recurring_trades_ended_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.col_bank_recurring_trades
    ADD CONSTRAINT col_bank_recurring_trades_ended_by_fkey FOREIGN KEY (ended_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: col_bank_recurring_trades col_bank_recurring_trades_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.col_bank_recurring_trades
    ADD CONSTRAINT col_bank_recurring_trades_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: col_bank_trades col_bank_trades_resolved_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.col_bank_trades
    ADD CONSTRAINT col_bank_trades_resolved_by_fkey FOREIGN KEY (resolved_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: col_bank_trades col_bank_trades_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.col_bank_trades
    ADD CONSTRAINT col_bank_trades_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: currency_holdings currency_holdings_issuer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.currency_holdings
    ADD CONSTRAINT currency_holdings_issuer_id_fkey FOREIGN KEY (issuer_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: currency_holdings currency_holdings_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.currency_holdings
    ADD CONSTRAINT currency_holdings_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: currency_market_offers currency_market_offers_issuer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.currency_market_offers
    ADD CONSTRAINT currency_market_offers_issuer_id_fkey FOREIGN KEY (issuer_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: currency_market_offers currency_market_offers_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.currency_market_offers
    ADD CONSTRAINT currency_market_offers_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: currency_market_trades currency_market_trades_buyer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.currency_market_trades
    ADD CONSTRAINT currency_market_trades_buyer_id_fkey FOREIGN KEY (buyer_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: currency_market_trades currency_market_trades_issuer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.currency_market_trades
    ADD CONSTRAINT currency_market_trades_issuer_id_fkey FOREIGN KEY (issuer_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: currency_market_trades currency_market_trades_seller_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.currency_market_trades
    ADD CONSTRAINT currency_market_trades_seller_id_fkey FOREIGN KEY (seller_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: currency_union_applications currency_union_applications_union_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.currency_union_applications
    ADD CONSTRAINT currency_union_applications_union_id_fkey FOREIGN KEY (union_id) REFERENCES public.currency_unions(id) ON DELETE CASCADE;


--
-- Name: currency_union_applications currency_union_applications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.currency_union_applications
    ADD CONSTRAINT currency_union_applications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: currency_union_members currency_union_members_union_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.currency_union_members
    ADD CONSTRAINT currency_union_members_union_id_fkey FOREIGN KEY (union_id) REFERENCES public.currency_unions(id) ON DELETE CASCADE;


--
-- Name: currency_union_members currency_union_members_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.currency_union_members
    ADD CONSTRAINT currency_union_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: currency_unions currency_unions_founder_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.currency_unions
    ADD CONSTRAINT currency_unions_founder_id_fkey FOREIGN KEY (founder_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: devlog_entries devlog_entries_author_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.devlog_entries
    ADD CONSTRAINT devlog_entries_author_id_fkey FOREIGN KEY (author_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: direct_messages direct_messages_recipient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.direct_messages
    ADD CONSTRAINT direct_messages_recipient_id_fkey FOREIGN KEY (recipient_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: direct_messages direct_messages_sender_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.direct_messages
    ADD CONSTRAINT direct_messages_sender_id_fkey FOREIGN KEY (sender_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: discord_guild_settings discord_guild_settings_coalition_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_guild_settings
    ADD CONSTRAINT discord_guild_settings_coalition_id_fkey FOREIGN KEY (coalition_id) REFERENCES public.colnames(id) ON DELETE SET NULL;


--
-- Name: discord_link_codes discord_link_codes_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.discord_link_codes
    ADD CONSTRAINT discord_link_codes_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: building_dictionary fk_building_required_tech; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.building_dictionary
    ADD CONSTRAINT fk_building_required_tech FOREIGN KEY (required_tech_id) REFERENCES public.tech_dictionary(tech_id) ON DELETE SET NULL;


--
-- Name: colbanksrequests fk_cbr_colid; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.colbanksrequests
    ADD CONSTRAINT fk_cbr_colid FOREIGN KEY (colid) REFERENCES public.colnames(id) ON DELETE CASCADE;


--
-- Name: colbanksrequests fk_cbr_reqid; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.colbanksrequests
    ADD CONSTRAINT fk_cbr_reqid FOREIGN KEY (reqid) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: coalitions_normalized fk_coalition_founder; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalitions_normalized
    ADD CONSTRAINT fk_coalition_founder FOREIGN KEY (founder_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: coalition_members fk_coalition_member_coalition; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalition_members
    ADD CONSTRAINT fk_coalition_member_coalition FOREIGN KEY (coalition_id) REFERENCES public.coalitions_normalized(coalition_id) ON DELETE CASCADE;


--
-- Name: coalition_members fk_coalition_member_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalition_members
    ADD CONSTRAINT fk_coalition_member_user FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: coalitions_legacy fk_coalitions_col; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalitions_legacy
    ADD CONSTRAINT fk_coalitions_col FOREIGN KEY (colid) REFERENCES public.colnames(id) ON DELETE CASCADE;


--
-- Name: coalitions_legacy fk_coalitions_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.coalitions_legacy
    ADD CONSTRAINT fk_coalitions_user FOREIGN KEY (userid) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: colbanks fk_colbanks_colnames; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.colbanks
    ADD CONSTRAINT fk_colbanks_colnames FOREIGN KEY (colid) REFERENCES public.colnames(id) ON DELETE CASCADE;


--
-- Name: global_market fk_global_market_fulfilled_by; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.global_market
    ADD CONSTRAINT fk_global_market_fulfilled_by FOREIGN KEY (fulfilled_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: global_market fk_global_market_resource; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.global_market
    ADD CONSTRAINT fk_global_market_resource FOREIGN KEY (resource_id) REFERENCES public.resource_dictionary(resource_id) ON DELETE RESTRICT;


--
-- Name: global_market fk_global_market_seller; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.global_market
    ADD CONSTRAINT fk_global_market_seller FOREIGN KEY (seller_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: map_objects fk_map_owner; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.map_objects
    ADD CONSTRAINT fk_map_owner FOREIGN KEY (owner_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: marches fk_marches_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.marches
    ADD CONSTRAINT fk_marches_user FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: military fk_military_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.military
    ADD CONSTRAINT fk_military_user FOREIGN KEY (id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: news fk_news_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.news
    ADD CONSTRAINT fk_news_user FOREIGN KEY (destination_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: offers fk_offers_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.offers
    ADD CONSTRAINT fk_offers_user FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: peace fk_peace_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.peace
    ADD CONSTRAINT fk_peace_user FOREIGN KEY (author) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: policies fk_policies_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.policies
    ADD CONSTRAINT fk_policies_user FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: proinfra fk_proinfra_province; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proinfra
    ADD CONSTRAINT fk_proinfra_province FOREIGN KEY (id) REFERENCES public.provinces(id) ON DELETE CASCADE;


--
-- Name: provinces fk_provinces_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.provinces
    ADD CONSTRAINT fk_provinces_user FOREIGN KEY (userid) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: reparation_tax fk_reptax_loser; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reparation_tax
    ADD CONSTRAINT fk_reptax_loser FOREIGN KEY (loser) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: reparation_tax fk_reptax_winner; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reparation_tax
    ADD CONSTRAINT fk_reptax_winner FOREIGN KEY (winner) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: requests fk_requests_colid; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requests
    ADD CONSTRAINT fk_requests_colid FOREIGN KEY (colid) REFERENCES public.colnames(id) ON DELETE CASCADE;


--
-- Name: requests fk_requests_reqid; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.requests
    ADD CONSTRAINT fk_requests_reqid FOREIGN KEY (reqid) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: reset_codes fk_reset_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reset_codes
    ADD CONSTRAINT fk_reset_user FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: resources fk_resources_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resources
    ADD CONSTRAINT fk_resources_user FOREIGN KEY (id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: revenue fk_revenue_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.revenue
    ADD CONSTRAINT fk_revenue_user FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: spyinfo fk_spyinfo_spyee; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.spyinfo
    ADD CONSTRAINT fk_spyinfo_spyee FOREIGN KEY (spyee) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: spyinfo fk_spyinfo_spyer; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.spyinfo
    ADD CONSTRAINT fk_spyinfo_spyer FOREIGN KEY (spyer) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: stats fk_stats_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stats
    ADD CONSTRAINT fk_stats_user FOREIGN KEY (id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: tech_dictionary fk_tech_prerequisite; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tech_dictionary
    ADD CONSTRAINT fk_tech_prerequisite FOREIGN KEY (prerequisite_tech_id) REFERENCES public.tech_dictionary(tech_id) ON DELETE SET NULL;


--
-- Name: trades fk_trades_offeree; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trades
    ADD CONSTRAINT fk_trades_offeree FOREIGN KEY (offeree) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: trades fk_trades_offerer; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.trades
    ADD CONSTRAINT fk_trades_offerer FOREIGN KEY (offerer) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: treaties fk_treaties_col1; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treaties
    ADD CONSTRAINT fk_treaties_col1 FOREIGN KEY (col1_id) REFERENCES public.colnames(id) ON DELETE CASCADE;


--
-- Name: treaties fk_treaties_col2; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.treaties
    ADD CONSTRAINT fk_treaties_col2 FOREIGN KEY (col2_id) REFERENCES public.colnames(id) ON DELETE CASCADE;


--
-- Name: unit_dictionary fk_unit_maintenance_resource; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.unit_dictionary
    ADD CONSTRAINT fk_unit_maintenance_resource FOREIGN KEY (maintenance_cost_resource_id) REFERENCES public.resource_dictionary(resource_id) ON DELETE SET NULL;


--
-- Name: upgrades fk_upgrades_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.upgrades
    ADD CONSTRAINT fk_upgrades_user FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_buildings fk_user_buildings_building; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_buildings
    ADD CONSTRAINT fk_user_buildings_building FOREIGN KEY (building_id) REFERENCES public.building_dictionary(building_id) ON DELETE RESTRICT;


--
-- Name: user_buildings fk_user_buildings_province; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_buildings
    ADD CONSTRAINT fk_user_buildings_province FOREIGN KEY (province_id) REFERENCES public.provinces(id) ON DELETE CASCADE;


--
-- Name: user_buildings fk_user_buildings_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_buildings
    ADD CONSTRAINT fk_user_buildings_user FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_economy fk_user_economy_resource; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_economy
    ADD CONSTRAINT fk_user_economy_resource FOREIGN KEY (resource_id) REFERENCES public.resource_dictionary(resource_id) ON DELETE RESTRICT;


--
-- Name: user_economy fk_user_economy_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_economy
    ADD CONSTRAINT fk_user_economy_user FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_military fk_user_military_unit; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_military
    ADD CONSTRAINT fk_user_military_unit FOREIGN KEY (unit_id) REFERENCES public.unit_dictionary(unit_id) ON DELETE RESTRICT;


--
-- Name: user_military fk_user_military_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_military
    ADD CONSTRAINT fk_user_military_user FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_tech fk_user_tech_tech; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_tech
    ADD CONSTRAINT fk_user_tech_tech FOREIGN KEY (tech_id) REFERENCES public.tech_dictionary(tech_id) ON DELETE RESTRICT;


--
-- Name: user_tech fk_user_tech_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_tech
    ADD CONSTRAINT fk_user_tech_user FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_unit_stockpile fk_user_unit_stockpile_unit; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_unit_stockpile
    ADD CONSTRAINT fk_user_unit_stockpile_unit FOREIGN KEY (unit_id) REFERENCES public.unit_dictionary(unit_id) ON DELETE RESTRICT;


--
-- Name: user_unit_stockpile fk_user_unit_stockpile_user; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_unit_stockpile
    ADD CONSTRAINT fk_user_unit_stockpile_user FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: wars fk_wars_attacker; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wars
    ADD CONSTRAINT fk_wars_attacker FOREIGN KEY (attacker) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: wars_normalized fk_wars_attacker; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wars_normalized
    ADD CONSTRAINT fk_wars_attacker FOREIGN KEY (attacker_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: wars fk_wars_defender; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wars
    ADD CONSTRAINT fk_wars_defender FOREIGN KEY (defender) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: wars_normalized fk_wars_defender; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wars_normalized
    ADD CONSTRAINT fk_wars_defender FOREIGN KEY (defender_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: wars fk_wars_peace; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wars
    ADD CONSTRAINT fk_wars_peace FOREIGN KEY (peace_offer_id) REFERENCES public.peace(id) ON DELETE SET NULL;


--
-- Name: wars_normalized fk_wars_winner; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.wars_normalized
    ADD CONSTRAINT fk_wars_winner FOREIGN KEY (winner_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: forum_replies forum_replies_author_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.forum_replies
    ADD CONSTRAINT forum_replies_author_id_fkey FOREIGN KEY (author_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: forum_replies forum_replies_thread_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.forum_replies
    ADD CONSTRAINT forum_replies_thread_id_fkey FOREIGN KEY (thread_id) REFERENCES public.forum_threads(id) ON DELETE CASCADE;


--
-- Name: forum_threads forum_threads_author_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.forum_threads
    ADD CONSTRAINT forum_threads_author_id_fkey FOREIGN KEY (author_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: gem_purchases gem_purchases_gem_package_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gem_purchases
    ADD CONSTRAINT gem_purchases_gem_package_id_fkey FOREIGN KEY (gem_package_id) REFERENCES public.gem_packages(id);


--
-- Name: gem_purchases gem_purchases_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.gem_purchases
    ADD CONSTRAINT gem_purchases_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: global_chat_messages global_chat_messages_sender_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.global_chat_messages
    ADD CONSTRAINT global_chat_messages_sender_id_fkey FOREIGN KEY (sender_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: interactive_events interactive_events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.interactive_events
    ADD CONSTRAINT interactive_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: login_events login_events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.login_events
    ADD CONSTRAINT login_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: login_verifications login_verifications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.login_verifications
    ADD CONSTRAINT login_verifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: map_combat_log map_combat_log_attacker_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.map_combat_log
    ADD CONSTRAINT map_combat_log_attacker_id_fkey FOREIGN KEY (attacker_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: map_combat_log map_combat_log_defender_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.map_combat_log
    ADD CONSTRAINT map_combat_log_defender_id_fkey FOREIGN KEY (defender_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: map_combat_log map_combat_log_province_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.map_combat_log
    ADD CONSTRAINT map_combat_log_province_id_fkey FOREIGN KEY (province_id) REFERENCES public.provinces(id) ON DELETE CASCADE;


--
-- Name: map_unit_deployments map_unit_deployments_province_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.map_unit_deployments
    ADD CONSTRAINT map_unit_deployments_province_id_fkey FOREIGN KEY (province_id) REFERENCES public.provinces(id) ON DELETE CASCADE;


--
-- Name: map_unit_deployments map_unit_deployments_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.map_unit_deployments
    ADD CONSTRAINT map_unit_deployments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: market_auto_order_log market_auto_order_log_auto_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_auto_order_log
    ADD CONSTRAINT market_auto_order_log_auto_order_id_fkey FOREIGN KEY (auto_order_id) REFERENCES public.market_auto_orders(id) ON DELETE CASCADE;


--
-- Name: market_auto_orders market_auto_orders_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_auto_orders
    ADD CONSTRAINT market_auto_orders_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: market_embargoes market_embargoes_embargoed_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_embargoes
    ADD CONSTRAINT market_embargoes_embargoed_id_fkey FOREIGN KEY (embargoed_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: market_embargoes market_embargoes_embargoer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_embargoes
    ADD CONSTRAINT market_embargoes_embargoer_id_fkey FOREIGN KEY (embargoer_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: market_preferences market_preferences_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_preferences
    ADD CONSTRAINT market_preferences_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: nation_treaties nation_treaties_recipient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nation_treaties
    ADD CONSTRAINT nation_treaties_recipient_id_fkey FOREIGN KEY (recipient_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: nation_treaties nation_treaties_sender_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nation_treaties
    ADD CONSTRAINT nation_treaties_sender_id_fkey FOREIGN KEY (sender_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: national_currency_conversions national_currency_conversions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.national_currency_conversions
    ADD CONSTRAINT national_currency_conversions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: node_battles node_battles_attacking_coalition_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_battles
    ADD CONSTRAINT node_battles_attacking_coalition_id_fkey FOREIGN KEY (attacking_coalition_id) REFERENCES public.colnames(id) ON DELETE CASCADE;


--
-- Name: node_battles node_battles_defending_coalition_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_battles
    ADD CONSTRAINT node_battles_defending_coalition_id_fkey FOREIGN KEY (defending_coalition_id) REFERENCES public.colnames(id) ON DELETE CASCADE;


--
-- Name: node_battles node_battles_node_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_battles
    ADD CONSTRAINT node_battles_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.nodes(id) ON DELETE CASCADE;


--
-- Name: node_yields node_yields_node_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.node_yields
    ADD CONSTRAINT node_yields_node_id_fkey FOREIGN KEY (node_id) REFERENCES public.nodes(id) ON DELETE CASCADE;


--
-- Name: nodes nodes_controlling_coalition_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nodes
    ADD CONSTRAINT nodes_controlling_coalition_id_fkey FOREIGN KEY (controlling_coalition_id) REFERENCES public.colnames(id) ON DELETE SET NULL;


--
-- Name: nuclear_strikes nuclear_strikes_attacker_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nuclear_strikes
    ADD CONSTRAINT nuclear_strikes_attacker_id_fkey FOREIGN KEY (attacker_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: nuclear_strikes nuclear_strikes_target_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nuclear_strikes
    ADD CONSTRAINT nuclear_strikes_target_id_fkey FOREIGN KEY (target_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: patreon_gem_grants patreon_gem_grants_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patreon_gem_grants
    ADD CONSTRAINT patreon_gem_grants_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: poll_votes poll_votes_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.poll_votes
    ADD CONSTRAINT poll_votes_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: population_growth_freezes population_growth_freezes_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.population_growth_freezes
    ADD CONSTRAINT population_growth_freezes_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: province_iron_domes province_iron_domes_province_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.province_iron_domes
    ADD CONSTRAINT province_iron_domes_province_id_fkey FOREIGN KEY (province_id) REFERENCES public.provinces(id) ON DELETE CASCADE;


--
-- Name: referral_active_days referral_active_days_referred_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_active_days
    ADD CONSTRAINT referral_active_days_referred_user_id_fkey FOREIGN KEY (referred_user_id) REFERENCES public.users(id);


--
-- Name: referral_milestone_payouts referral_milestone_payouts_referred_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_milestone_payouts
    ADD CONSTRAINT referral_milestone_payouts_referred_user_id_fkey FOREIGN KEY (referred_user_id) REFERENCES public.users(id);


--
-- Name: referral_milestone_payouts referral_milestone_payouts_referrer_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.referral_milestone_payouts
    ADD CONSTRAINT referral_milestone_payouts_referrer_user_id_fkey FOREIGN KEY (referrer_user_id) REFERENCES public.users(id);


--
-- Name: stats stats_equipped_background_cosmetic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stats
    ADD CONSTRAINT stats_equipped_background_cosmetic_id_fkey FOREIGN KEY (equipped_background_cosmetic_id) REFERENCES public.cosmetics(id) ON DELETE SET NULL;


--
-- Name: stats stats_equipped_badge_cosmetic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stats
    ADD CONSTRAINT stats_equipped_badge_cosmetic_id_fkey FOREIGN KEY (equipped_badge_cosmetic_id) REFERENCES public.cosmetics(id) ON DELETE SET NULL;


--
-- Name: stats stats_equipped_country_border_cosmetic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stats
    ADD CONSTRAINT stats_equipped_country_border_cosmetic_id_fkey FOREIGN KEY (equipped_country_border_cosmetic_id) REFERENCES public.cosmetics(id) ON DELETE SET NULL;


--
-- Name: stats stats_equipped_name_color_cosmetic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stats
    ADD CONSTRAINT stats_equipped_name_color_cosmetic_id_fkey FOREIGN KEY (equipped_name_color_cosmetic_id) REFERENCES public.cosmetics(id) ON DELETE SET NULL;


--
-- Name: stats stats_equipped_title_cosmetic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.stats
    ADD CONSTRAINT stats_equipped_title_cosmetic_id_fkey FOREIGN KEY (equipped_title_cosmetic_id) REFERENCES public.cosmetics(id) ON DELETE SET NULL;


--
-- Name: totp_backup_codes totp_backup_codes_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.totp_backup_codes
    ADD CONSTRAINT totp_backup_codes_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_achievements user_achievements_key_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_achievements
    ADD CONSTRAINT user_achievements_key_fkey FOREIGN KEY (key) REFERENCES public.achievements(key) ON DELETE CASCADE;


--
-- Name: user_achievements user_achievements_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_achievements
    ADD CONSTRAINT user_achievements_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_cosmetics user_cosmetics_cosmetic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_cosmetics
    ADD CONSTRAINT user_cosmetics_cosmetic_id_fkey FOREIGN KEY (cosmetic_id) REFERENCES public.cosmetics(id) ON DELETE CASCADE;


--
-- Name: user_cosmetics user_cosmetics_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_cosmetics
    ADD CONSTRAINT user_cosmetics_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_loans user_loans_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_loans
    ADD CONSTRAINT user_loans_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: users users_referred_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_referred_by_user_id_fkey FOREIGN KEY (referred_by_user_id) REFERENCES public.users(id);


--
-- Name: world_events world_events_actor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.world_events
    ADD CONSTRAINT world_events_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: world_events world_events_target_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.world_events
    ADD CONSTRAINT world_events_target_id_fkey FOREIGN KEY (target_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--


