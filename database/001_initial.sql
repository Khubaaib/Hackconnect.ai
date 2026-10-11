BEGIN;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TABLE IF NOT EXISTS schema_migrations(version text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE user_profiles (
 id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
 display_name text NOT NULL DEFAULT '' CHECK(length(display_name)<=100),
 institution text NOT NULL DEFAULT '', degree text NOT NULL DEFAULT '', year_of_study text NOT NULL DEFAULT '',
 city text NOT NULL DEFAULT '', country text NOT NULL DEFAULT '', timezone text NOT NULL DEFAULT 'UTC', bio text NOT NULL DEFAULT '',
 github_url text, linkedin_url text, portfolio_url text, avatar_url text,
 roles text[] NOT NULL DEFAULT '{}', interests text[] NOT NULL DEFAULT '{}', format text NOT NULL DEFAULT 'any' CHECK(format IN ('any','online','offline','hybrid')),
 travel_willing boolean NOT NULL DEFAULT false, preferred_team_size int NOT NULL DEFAULT 4 CHECK(preferred_team_size BETWEEN 2 AND 10),
 experience int NOT NULL DEFAULT 0 CHECK(experience>=0), onboarding_step int NOT NULL DEFAULT 0 CHECK(onboarding_step BETWEEN 0 AND 6),
 onboarding_complete boolean NOT NULL DEFAULT false, discoverable boolean NOT NULL DEFAULT false, open_to_invitations boolean NOT NULL DEFAULT false,
 contact_consent boolean NOT NULL DEFAULT false, ai_consent boolean NOT NULL DEFAULT false,
 visibility jsonb NOT NULL DEFAULT '{"institution":true,"city":false,"links":true}',
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE user_roles(user_id uuid REFERENCES user_profiles ON DELETE CASCADE, role text CHECK(role IN ('student','admin')), PRIMARY KEY(user_id,role));
CREATE TABLE profile_preferences(user_id uuid PRIMARY KEY REFERENCES user_profiles ON DELETE CASCADE, notification_preferences jsonb NOT NULL DEFAULT '{}');
CREATE TABLE user_availability(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),user_id uuid NOT NULL REFERENCES user_profiles ON DELETE CASCADE, starts_at timestamptz NOT NULL, ends_at timestamptz NOT NULL, CHECK(ends_at>starts_at));
CREATE TABLE skill_categories(id text PRIMARY KEY, name text NOT NULL);
INSERT INTO skill_categories VALUES ('technical','Technical'),('nontechnical','Nontechnical');
CREATE TABLE skills(id text PRIMARY KEY,name text NOT NULL,category text NOT NULL REFERENCES skill_categories);
CREATE TABLE user_skills(user_id uuid REFERENCES user_profiles ON DELETE CASCADE,skill_id text REFERENCES skills, proficiency int CHECK(proficiency BETWEEN 1 AND 3),PRIMARY KEY(user_id,skill_id));
CREATE TABLE hackathon_sources(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),name text NOT NULL,kind text NOT NULL, reference text NOT NULL UNIQUE,authorized boolean NOT NULL DEFAULT false);
CREATE TABLE hackathons(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), title text NOT NULL, description text NOT NULL DEFAULT '',organizer text,
 domains text[] NOT NULL DEFAULT '{}', roles text[] NOT NULL DEFAULT '{}',registration_url text NOT NULL,source_url text NOT NULL,
 source_id uuid REFERENCES hackathon_sources, source_reference text, registration_opens_at timestamptz,registration_deadline timestamptz,starts_at timestamptz,ends_at timestamptz,
 format text NOT NULL DEFAULT 'online' CHECK(format IN ('online','offline','hybrid')), location text,country text,eligibility text,
 eligible_countries text[] NOT NULL DEFAULT '{}',student_only boolean NOT NULL DEFAULT false,
 minimum_team_size int NOT NULL DEFAULT 2 CHECK(minimum_team_size>=1),maximum_team_size int NOT NULL DEFAULT 4 CHECK(maximum_team_size BETWEEN 1 AND 10),
 prizes text, cancelled boolean NOT NULL DEFAULT false,registration_closed boolean NOT NULL DEFAULT false,
 verification_status text NOT NULL DEFAULT 'pending' CHECK(verification_status IN ('pending','verified','needs_correction','rejected')),
 quality_flags text[] NOT NULL DEFAULT '{}',last_verified_at timestamptz,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(source_id,source_reference),CHECK(maximum_team_size>=minimum_team_size),CHECK(ends_at IS NULL OR starts_at IS NULL OR ends_at>=starts_at),CHECK(registration_deadline IS NULL OR registration_opens_at IS NULL OR registration_deadline>=registration_opens_at)
);
CREATE TABLE hackathon_requirements(hackathon_id uuid REFERENCES hackathons ON DELETE CASCADE,skill_id text REFERENCES skills,proficiency int NOT NULL DEFAULT 1 CHECK(proficiency BETWEEN 1 AND 3),PRIMARY KEY(hackathon_id,skill_id));
CREATE INDEX hackathon_active ON hackathons(verification_status,registration_deadline,starts_at);
CREATE TABLE ingestion_events(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),source_id uuid REFERENCES hackathon_sources,reference text NOT NULL,payload jsonb NOT NULL,status text NOT NULL DEFAULT 'pending',error text,updated_at timestamptz NOT NULL DEFAULT now(),UNIQUE(source_id,reference));
CREATE TABLE hackathon_bookmarks(user_id uuid REFERENCES user_profiles ON DELETE CASCADE,hackathon_id uuid REFERENCES hackathons ON DELETE CASCADE,PRIMARY KEY(user_id,hackathon_id));
CREATE TABLE recommendation_feedback(user_id uuid REFERENCES user_profiles ON DELETE CASCADE,hackathon_id uuid REFERENCES hackathons ON DELETE CASCADE,feedback text CHECK(feedback IN ('hide','interested')),PRIMARY KEY(user_id,hackathon_id));
CREATE TABLE recommendation_versions(version text PRIMARY KEY,weights jsonb NOT NULL);
INSERT INTO recommendation_versions VALUES ('v1','{"skills":0.30,"interests":0.25,"roles":0.15,"schedule":0.10,"experience":0.10,"format":0.10}');
CREATE TABLE hackathon_recommendations(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),user_id uuid REFERENCES user_profiles ON DELETE CASCADE,hackathon_id uuid REFERENCES hackathons ON DELETE CASCADE,version text REFERENCES recommendation_versions,input_hash text NOT NULL,result jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(user_id,hackathon_id,version,input_hash));
CREATE TABLE teammate_recommendations(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),user_id uuid REFERENCES user_profiles ON DELETE CASCADE,candidate_id uuid REFERENCES user_profiles ON DELETE CASCADE,hackathon_id uuid REFERENCES hackathons ON DELETE CASCADE,result jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE teams(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),hackathon_id uuid NOT NULL REFERENCES hackathons,name text NOT NULL CHECK(length(name) BETWEEN 1 AND 100),leader_id uuid NOT NULL REFERENCES user_profiles,ai_consent boolean NOT NULL DEFAULT false,created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(id,hackathon_id));
CREATE TABLE team_roles(id text PRIMARY KEY,name text NOT NULL);
INSERT INTO team_roles VALUES ('member','Member'),('leader','Leader');
CREATE TABLE team_members(team_id uuid REFERENCES teams ON DELETE CASCADE,user_id uuid REFERENCES user_profiles ON DELETE CASCADE,hackathon_id uuid NOT NULL REFERENCES hackathons,role text NOT NULL DEFAULT 'member',assigned_role text NOT NULL DEFAULT '',joined_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(team_id,user_id),UNIQUE(hackathon_id,user_id),FOREIGN KEY(team_id,hackathon_id) REFERENCES teams(id,hackathon_id) ON DELETE CASCADE);
CREATE INDEX members_user ON team_members(user_id);
CREATE TABLE team_invitations(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),team_id uuid REFERENCES teams ON DELETE CASCADE,sender_id uuid REFERENCES user_profiles ON DELETE CASCADE,recipient_id uuid REFERENCES user_profiles ON DELETE CASCADE,status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted','declined','cancelled')),created_at timestamptz NOT NULL DEFAULT now(),responded_at timestamptz, CHECK(sender_id<>recipient_id));
CREATE UNIQUE INDEX pending_invite ON team_invitations(team_id,recipient_id) WHERE status='pending';
CREATE TABLE team_messages(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),team_id uuid REFERENCES teams ON DELETE CASCADE,sender_id uuid REFERENCES user_profiles ON DELETE SET NULL,body text NOT NULL CHECK(length(body) BETWEEN 1 AND 4000),edited_at timestamptz,deleted_at timestamptz,created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX messages_page ON team_messages(team_id,created_at DESC);
CREATE TABLE project_tasks(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),team_id uuid REFERENCES teams ON DELETE CASCADE,title text NOT NULL CHECK(length(title) BETWEEN 1 AND 200),description text NOT NULL DEFAULT '',assignee_id uuid REFERENCES user_profiles ON DELETE SET NULL,priority text NOT NULL DEFAULT 'medium' CHECK(priority IN ('low','medium','high')),deadline timestamptz,status text NOT NULL DEFAULT 'todo' CHECK(status IN ('todo','in_progress','in_review','completed')),created_by uuid REFERENCES user_profiles ON DELETE SET NULL,version int NOT NULL DEFAULT 1,created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE milestones(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),team_id uuid REFERENCES teams ON DELETE CASCADE,title text NOT NULL,completed boolean NOT NULL DEFAULT false,deadline timestamptz);
CREATE TABLE task_comments(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),task_id uuid REFERENCES project_tasks ON DELETE CASCADE,user_id uuid REFERENCES user_profiles ON DELETE SET NULL,body text NOT NULL CHECK(length(body) BETWEEN 1 AND 2000),created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE project_resources(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),team_id uuid REFERENCES teams ON DELETE CASCADE,title text NOT NULL,url text NOT NULL,created_by uuid REFERENCES user_profiles ON DELETE SET NULL,created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE team_activity(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),team_id uuid REFERENCES teams ON DELETE CASCADE,actor_id uuid REFERENCES user_profiles ON DELETE SET NULL,action text NOT NULL,details jsonb NOT NULL DEFAULT '{}',created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE notifications(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),user_id uuid REFERENCES user_profiles ON DELETE CASCADE,kind text NOT NULL,title text NOT NULL,link text,read_at timestamptz,created_at timestamptz NOT NULL DEFAULT now(),dedupe_key text,UNIQUE(user_id,dedupe_key));
CREATE INDEX notification_user ON notifications(user_id,created_at DESC);
CREATE TABLE message_read_cursors(team_id uuid REFERENCES teams ON DELETE CASCADE,user_id uuid REFERENCES user_profiles ON DELETE CASCADE,read_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(team_id,user_id));
CREATE TABLE import_jobs(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),actor_id uuid REFERENCES user_profiles ON DELETE SET NULL,digest text NOT NULL UNIQUE,summary jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE imported_students(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),email text NOT NULL UNIQUE,display_name text NOT NULL,skills jsonb NOT NULL DEFAULT '[]',institution text NOT NULL DEFAULT '',claimed_by uuid UNIQUE REFERENCES user_profiles ON DELETE SET NULL,import_job_id uuid REFERENCES import_jobs ON DELETE SET NULL,created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE background_jobs(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),kind text NOT NULL,status text NOT NULL,summary jsonb NOT NULL DEFAULT '{}',created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE audit_logs(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),actor_id uuid REFERENCES user_profiles ON DELETE SET NULL,action text NOT NULL,target text,details jsonb NOT NULL DEFAULT '{}',created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE abuse_reports(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),reporter_id uuid REFERENCES user_profiles ON DELETE SET NULL,target_user_id uuid REFERENCES user_profiles ON DELETE SET NULL,reason text NOT NULL,status text NOT NULL DEFAULT 'open',created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE user_blocks(blocker_id uuid REFERENCES user_profiles ON DELETE CASCADE,blocked_id uuid REFERENCES user_profiles ON DELETE CASCADE,PRIMARY KEY(blocker_id,blocked_id),CHECK(blocker_id<>blocked_id));
CREATE TABLE api_rate_limits(user_id uuid PRIMARY KEY REFERENCES user_profiles ON DELETE CASCADE,bucket timestamptz NOT NULL,count int NOT NULL DEFAULT 0);
CREATE TABLE ai_usage(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),user_id uuid REFERENCES user_profiles ON DELETE SET NULL,team_id uuid REFERENCES teams ON DELETE CASCADE,request_id uuid NOT NULL DEFAULT gen_random_uuid(),status text NOT NULL DEFAULT 'reserved',input_tokens int NOT NULL DEFAULT 0,output_tokens int NOT NULL DEFAULT 0,created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE ai_cache(key text PRIMARY KEY,user_id uuid REFERENCES user_profiles ON DELETE CASCADE,team_id uuid REFERENCES teams ON DELETE CASCADE,result jsonb NOT NULL,expires_at timestamptz NOT NULL);
CREATE OR REPLACE FUNCTION public.is_admin() RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$SELECT EXISTS(SELECT 1 FROM user_roles WHERE user_id=auth.uid() AND role='admin')$$;
CREATE OR REPLACE FUNCTION public.is_team_member(t uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$SELECT EXISTS(SELECT 1 FROM team_members WHERE team_id=t AND user_id=auth.uid())$$;
CREATE OR REPLACE FUNCTION public.can_discover(u uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=public AS $$SELECT EXISTS(SELECT 1 FROM user_profiles WHERE id=u AND onboarding_complete AND discoverable AND contact_consent) AND NOT EXISTS(SELECT 1 FROM user_blocks WHERE (blocker_id=auth.uid() AND blocked_id=u) OR (blocked_id=auth.uid() AND blocker_id=u))$$;
-- Client receives safe fields through the backend, never a full discoverable profile row.
DO $$DECLARE t text;BEGIN FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='public' LOOP EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t);END LOOP;END$$;
CREATE POLICY profile_self ON user_profiles FOR SELECT TO authenticated USING(id=auth.uid());
CREATE POLICY role_self ON user_roles FOR SELECT TO authenticated USING(user_id=auth.uid());
CREATE POLICY skill_catalog ON skills FOR SELECT TO authenticated USING(true);
CREATE POLICY category_catalog ON skill_categories FOR SELECT TO authenticated USING(true);
CREATE POLICY my_skills ON user_skills FOR SELECT TO authenticated USING(user_id=auth.uid());
CREATE POLICY my_preferences ON profile_preferences FOR SELECT TO authenticated USING(user_id=auth.uid());
CREATE POLICY my_availability ON user_availability FOR SELECT TO authenticated USING(user_id=auth.uid());
CREATE POLICY visible_hackathons ON hackathons FOR SELECT TO authenticated USING(verification_status='verified' OR is_admin());
CREATE POLICY visible_requirements ON hackathon_requirements FOR SELECT TO authenticated USING(EXISTS(SELECT 1 FROM hackathons h WHERE h.id=hackathon_id));
CREATE POLICY my_bookmarks ON hackathon_bookmarks FOR SELECT TO authenticated USING(user_id=auth.uid());
CREATE POLICY my_feedback ON recommendation_feedback FOR SELECT TO authenticated USING(user_id=auth.uid());
CREATE POLICY my_notifications ON notifications FOR SELECT TO authenticated USING(user_id=auth.uid());
CREATE POLICY my_cursors ON message_read_cursors FOR SELECT TO authenticated USING(user_id=auth.uid());
CREATE POLICY my_blocks ON user_blocks FOR SELECT TO authenticated USING(blocker_id=auth.uid());
CREATE POLICY teams_member ON teams FOR SELECT TO authenticated USING(is_team_member(id));
CREATE POLICY members_member ON team_members FOR SELECT TO authenticated USING(is_team_member(team_id));
CREATE POLICY invitations_party ON team_invitations FOR SELECT TO authenticated USING(recipient_id=auth.uid() OR sender_id=auth.uid() OR is_team_member(team_id));
CREATE POLICY messages_member ON team_messages FOR SELECT TO authenticated USING(is_team_member(team_id));
CREATE POLICY tasks_member ON project_tasks FOR SELECT TO authenticated USING(is_team_member(team_id));
CREATE POLICY milestones_member ON milestones FOR SELECT TO authenticated USING(is_team_member(team_id));
CREATE POLICY resources_member ON project_resources FOR SELECT TO authenticated USING(is_team_member(team_id));
CREATE POLICY activity_member ON team_activity FOR SELECT TO authenticated USING(is_team_member(team_id));
CREATE POLICY comments_member ON task_comments FOR SELECT TO authenticated USING(EXISTS(SELECT 1 FROM project_tasks t WHERE t.id=task_id));
-- No browser writes: all mutations go through authenticated, authorized FastAPI transactions.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon,authenticated;
GRANT USAGE ON SCHEMA public TO authenticated;
GRANT SELECT ON user_profiles,user_roles,skills,skill_categories,user_skills,profile_preferences,user_availability,hackathons,hackathon_requirements,hackathon_bookmarks,recommendation_feedback,notifications,message_read_cursors,user_blocks,teams,team_members,team_invitations,team_messages,project_tasks,milestones,project_resources,team_activity,task_comments TO authenticated;
REVOKE ALL ON FUNCTION public.is_admin(),public.is_team_member(uuid),public.can_discover(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.is_admin(),public.is_team_member(uuid),public.can_discover(uuid) TO authenticated;
DO $$BEGIN IF EXISTS(SELECT 1 FROM pg_publication WHERE pubname='supabase_realtime') THEN ALTER PUBLICATION supabase_realtime ADD TABLE team_messages,project_tasks,milestones,notifications;END IF;END$$;
INSERT INTO schema_migrations(version) VALUES('001');
COMMIT;
