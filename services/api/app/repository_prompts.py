from __future__ import annotations

from typing import Optional
from .models import PromptConfig

class PromptsRepository:
    def ensure_prompt_defaults(self, prompts: list[PromptConfig]) -> None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                for prompt in prompts:
                    cursor.execute(
                        """
                        INSERT INTO prompt_configs (
                            id,
                            agent_key,
                            name,
                            version,
                            status,
                            system_prompt,
                            user_prompt_template,
                            model,
                            provider,
                            notes
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            prompt.id,
                            prompt.agent_key,
                            prompt.name,
                            prompt.version,
                            prompt.status,
                            prompt.system_prompt,
                            prompt.user_prompt_template,
                            prompt.model,
                            prompt.provider,
                            prompt.notes,
                        ),
                    )
            connection.commit()

    def list_prompt_configs(self, agent_key: Optional[str] = None) -> list[PromptConfig]:
        statement = """
            SELECT
                id,
                agent_key,
                name,
                version,
                status,
                system_prompt,
                user_prompt_template,
                model,
                provider,
                notes,
                created_at
            FROM prompt_configs
        """
        params: tuple[object, ...] = ()

        if agent_key:
            statement += " WHERE agent_key = %s"
            params = (agent_key,)

        statement += " ORDER BY agent_key ASC, version DESC"

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, params)
                rows = cursor.fetchall()

        return [self._map_prompt_row(row) for row in rows]

    def get_active_prompt(self, agent_key: str) -> PromptConfig:
        statement = """
            SELECT
                id,
                agent_key,
                name,
                version,
                status,
                system_prompt,
                user_prompt_template,
                model,
                provider,
                notes,
                created_at
            FROM prompt_configs
            WHERE agent_key = %s AND status = 'active'
            ORDER BY version DESC
            LIMIT 1
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (agent_key,))
                row = cursor.fetchone()

        if row is None:
            raise LookupError(f"No active prompt config found for {agent_key}.")

        return self._map_prompt_row(row)

    def create_prompt_version(
        self,
        *,
        agent_key: str,
        name: str,
        system_prompt: str,
        user_prompt_template: str,
        model: str,
        notes: str = "",
        activate: bool = True,
    ) -> PromptConfig:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COALESCE(MAX(version), 0) FROM prompt_configs WHERE agent_key = %s",
                    (agent_key,),
                )
                next_version = int(cursor.fetchone()[0]) + 1

                if activate:
                    cursor.execute(
                        "UPDATE prompt_configs SET status = 'archived' WHERE agent_key = %s AND status = 'active'",
                        (agent_key,),
                    )

                prompt_id = f"prompt:{agent_key}:v{next_version}"
                cursor.execute(
                    """
                    INSERT INTO prompt_configs (
                        id,
                        agent_key,
                        name,
                        version,
                        status,
                        system_prompt,
                        user_prompt_template,
                        model,
                        provider,
                        notes
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        prompt_id,
                        agent_key,
                        name,
                        next_version,
                        "active" if activate else "draft",
                        system_prompt,
                        user_prompt_template,
                        model,
                        "internal",
                        notes,
                    ),
                )
            connection.commit()

        return self.get_prompt(prompt_id)

    def get_prompt(self, prompt_id: str) -> PromptConfig:
        statement = """
            SELECT
                id,
                agent_key,
                name,
                version,
                status,
                system_prompt,
                user_prompt_template,
                model,
                provider,
                notes,
                created_at
            FROM prompt_configs
            WHERE id = %s
        """

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(statement, (prompt_id,))
                row = cursor.fetchone()

        if row is None:
            raise LookupError(f"Prompt {prompt_id} was not found.")

        return self._map_prompt_row(row)

    def set_prompt_status(self, prompt_id: str, status: str) -> PromptConfig:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT agent_key FROM prompt_configs WHERE id = %s", (prompt_id,))
                row = cursor.fetchone()
                if row is None:
                    raise LookupError(f"Prompt {prompt_id} was not found.")

                agent_key = str(row[0])
                if status == "active":
                    cursor.execute(
                        "UPDATE prompt_configs SET status = 'archived' WHERE agent_key = %s AND status = 'active'",
                        (agent_key,),
                    )

                cursor.execute(
                    "UPDATE prompt_configs SET status = %s WHERE id = %s",
                    (status, prompt_id),
                )
            connection.commit()

        return self.get_prompt(prompt_id)

    def delete_archived_prompt_versions(self) -> int:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM prompt_configs WHERE status <> 'active'")
                deleted_count = cursor.rowcount or 0
            connection.commit()

        return int(deleted_count)

    def maybe_activate_recommended_prompt(self, agent_key: str, recommended_prompt_id: str) -> None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM prompt_configs WHERE id = %s", (recommended_prompt_id,))
                if cursor.fetchone() is None:
                    return

                cursor.execute(
                    """
                    SELECT id, name, notes
                    FROM prompt_configs
                    WHERE agent_key = %s AND status = 'active'
                    ORDER BY version DESC
                    LIMIT 1
                    """,
                    (agent_key,),
                )
                row = cursor.fetchone()
                if row is None:
                    cursor.execute(
                        "UPDATE prompt_configs SET status = 'active' WHERE id = %s",
                        (recommended_prompt_id,),
                    )
                    connection.commit()
                    return

                active_id = str(row[0])
                active_name = str(row[1] or "")
                active_notes = str(row[2] or "")
                legacy_system_prompt_ids = {
                    "writer": {
                        "prompt:writer:v1",
                        "prompt:writer:v2",
                        "prompt:writer:v3",
                        "prompt:writer:v4",
                        "prompt:writer:v5",
                        "prompt:writer:v6",
                        "prompt:writer:v7",
                        "prompt:writer:v8",
                    },
                    "editor": {
                        "prompt:editor:v1",
                        "prompt:editor:v2",
                        "prompt:editor:v3",
                        "prompt:editor:v4",
                        "prompt:editor:v5",
                        "prompt:editor:v6",
                        "prompt:editor:v7",
                        "prompt:editor:v8",
                        "prompt:editor:v9",
                        "prompt:editor:v10",
                    },
                    "guide_writer": {"prompt:guide-writer:v1", "prompt:guide-writer:v2"},
                    "guide_editor": {"prompt:guide-editor:v1"},
                }
                legacy_default_names = {
                    "writer": {"Writer Editorial v1", "Writer Editorial v2", "Writer Editorial v3"},
                    "editor": {"Editor Editorial v1", "Editor Editorial v2", "Editor Editorial v3"},
                }
                is_legacy_system_prompt = (
                    active_id in legacy_system_prompt_ids.get(agent_key, set())
                    or active_name in legacy_default_names.get(agent_key, set())
                    or active_notes.startswith("Recommended default writer prompt")
                    or active_notes.startswith("Recommended default editor prompt")
                    or active_notes.startswith("Author-style writer prompt")
                    or active_notes.startswith("Chief editor prompt")
                )
                if not is_legacy_system_prompt:
                    return

                cursor.execute(
                    "UPDATE prompt_configs SET status = 'archived' WHERE agent_key = %s AND status = 'active'",
                    (agent_key,),
                )
                cursor.execute(
                    "UPDATE prompt_configs SET status = 'active' WHERE id = %s",
                    (recommended_prompt_id,),
                )
            connection.commit()

