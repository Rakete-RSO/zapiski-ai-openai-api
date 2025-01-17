import strawberry

@strawberry.type
class Query:
    @strawberry.field
    def get_chatgpt_version(self) -> str:
        """
        Returns the version of ChatGPT being used.
        """
        return "ChatGPT-4"

schema = strawberry.Schema(query=Query)